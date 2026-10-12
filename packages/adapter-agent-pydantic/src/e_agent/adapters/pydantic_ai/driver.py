"""AgentDriver backed by Pydantic AI 2.x.

Every capability is exposed as an *external* (deferred) tool: the model can only
request calls, and each request comes back to the kernel as DeferredToolRequests.
Reads are executed by the kernel gateway; a write becomes a proposal that goes
through validation, approval, dispatch and verification. Results resume the run
via DeferredToolResults. Nothing effectful executes inside the framework, and
framework approval (`requires_approval`) is never used (ADR 0004).

Continuation hygiene: ThinkingPart content is removed from the stored history
and never leaves the driver (AGENTS.md: no persisted hidden reasoning).
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import AsyncIterable, Mapping, Sequence
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from e_agent.contracts.capability import EffectKind
from e_agent.contracts.context import TaskContext
from e_agent.contracts.plan import ActionProposal
from e_agent.sdk.errors import DriverBudgetExceeded
from e_agent.sdk.ports import (
    AskClarification,
    DriverInput,
    DriverStep,
    FinalAnswer,
    ProposeAction,
    ReadRequest,
    RequestReads,
    SafeTextSink,
)
from pydantic_core import to_jsonable_python

import pydantic_ai
from pydantic_ai import (
    Agent,
    DeferredToolRequests,
    DeferredToolResults,
    ExternalToolset,
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    ToolDefinition,
)
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    AgentStreamEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
)
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage, UsageLimits

STATE_SCHEMA = "pydantic-ai-driver-v1"

BASE_INSTRUCTIONS = (
    "You are e-agent, an enterprise assistant that works only through the tools provided. "
    "Use read tools to obtain facts; never invent facts or tool results. Resource references "
    "are opaque identifiers: copy their complete exact value from tool data or the user, "
    "including every prefix before a colon or slash. Never shorten them to display names. "
    "To change "
    "anything, call exactly one write tool with complete arguments; it is a proposal that a "
    "human must approve, and you will receive its result or the rule findings that blocked "
    "it. Do not claim an action happened until a tool result says it was verified. "
    "Use a structured answer tool when one is provided for the task, before final text; "
    "the host must verify the answer. If necessary user details are missing, call "
    "request_clarification with one concise question. Answer briefly in the user's language."
)


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    """A capability exposed to the model. Built by the host from registry data."""

    contract_id: str
    effect: EffectKind
    description: str
    parameters: Mapping[str, Any]
    connection_id: str

    @property
    def name(self) -> str:
        return re.sub(r"[^a-zA-Z0-9_]", "_", self.contract_id)


@dataclasses.dataclass
class _RunState:
    messages: list[ModelMessage] = dataclasses.field(default_factory=list)
    pending_reads: dict[str, str] = dataclasses.field(default_factory=dict)  # call id -> contract
    pending_write: str | None = None
    pending_input: str | None = None
    tokens: int = 0
    rejected: dict[str, str] = dataclasses.field(default_factory=dict)  # call id -> reason


class _PublicTextFilter:
    """Suppress reasoning tags even when a provider places them in text deltas."""

    def __init__(self) -> None:
        self.buffer = ""
        self.closing: str | None = None

    def feed(self, text: str, *, final: bool = False) -> str:
        self.buffer += text
        public = ""
        tags = {"<think>": "</think>", "<analysis>": "</analysis>", "<reasoning>": "</reasoning>"}
        while self.buffer:
            lower = self.buffer.lower()
            if self.closing is not None:
                end = lower.find(self.closing)
                if end < 0:
                    self.buffer = self.buffer[-(len(self.closing) - 1) :]
                    break
                self.buffer = self.buffer[end + len(self.closing) :]
                self.closing = None
                continue
            matches = [(lower.find(tag), tag) for tag in tags if tag in lower]
            if matches:
                start, tag = min(matches)
                public += self.buffer[:start]
                self.buffer = self.buffer[start + len(tag) :]
                self.closing = tags[tag]
                continue
            keep = max(
                (
                    length
                    for tag in tags
                    for length in range(1, len(tag))
                    if lower.endswith(tag[:length])
                ),
                default=0,
            )
            if keep:
                public += self.buffer[:-keep]
                self.buffer = "" if final else self.buffer[-keep:]
            else:
                public += self.buffer
                self.buffer = ""
            break
        return public


def _public_text(text: str) -> str:
    return _PublicTextFilter().feed(text, final=True)


def strip_thinking(messages: Sequence[ModelMessage]) -> list[ModelMessage]:
    cleaned: list[ModelMessage] = []
    for message in messages:
        if isinstance(message, ModelResponse):
            text_filter = _PublicTextFilter()
            parts = []
            for part in message.parts:
                if isinstance(part, ThinkingPart):
                    continue
                if isinstance(part, TextPart):
                    part = dataclasses.replace(part, content=text_filter.feed(part.content))
                parts.append(part)
            tail = text_filter.feed("", final=True)
            if tail:
                parts.append(TextPart(tail))
            message = dataclasses.replace(message, parts=parts, provider_details=None)
        cleaned.append(message)
    return cleaned


def _coerce(value: Any, schema: Mapping[str, Any] | None) -> Any:
    """Schema-guided, lossless coercion of numbers to decimal strings."""
    if schema is not None and schema.get("type") == "string":
        if isinstance(value, bool):
            return value
        if isinstance(value, int | float):
            return format(Decimal(str(value)).normalize(), "f")
    return value


def ollama_model(model_name: str, base_url: str) -> Model:
    endpoint = urlsplit(base_url)
    if (
        endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}
        or endpoint.scheme != "http"
        or endpoint.username
        or endpoint.query
        or endpoint.fragment
        or model_name.endswith(("-cloud", ":cloud"))
    ):
        raise ValueError("MVP inference requires a local Ollama endpoint and a local model")
    from pydantic_ai.models.ollama import OllamaModel
    from pydantic_ai.providers.ollama import OllamaProvider

    return OllamaModel(model_name, provider=OllamaProvider(base_url=base_url))


class PydanticAiDriver:
    driver_id = "pydantic-ai"

    def __init__(
        self,
        model: Model | str,
        tools: Sequence[ToolSpec],
        *,
        guidance: Sequence[str] = (),
        requests_per_step: int = 4,
        model_settings: Mapping[str, Any] | None = None,
    ) -> None:
        self._tools = {t.name: t for t in tools}
        self._toolset = ExternalToolset(
            [
                ToolDefinition(
                    name=t.name,
                    description=t.description,
                    parameters_json_schema=dict(t.parameters),
                )
                for t in tools
            ]
            + [
                ToolDefinition(
                    name="request_clarification",
                    description=(
                        "Ask the user for required missing task details. "
                        "This grants no approval or authority."
                    ),
                    parameters_json_schema={
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "minLength": 1, "maxLength": 4000}
                        },
                        "required": ["question"],
                        "additionalProperties": False,
                    },
                )
            ]
        )
        instructions = "\n\n".join([BASE_INSTRUCTIONS, *guidance])
        self._agent: Agent[None, str | DeferredToolRequests] = Agent(
            model,
            instructions=instructions,
            output_type=[str, DeferredToolRequests],
        )
        self._limits = UsageLimits(request_limit=requests_per_step)
        self._settings = dict(model_settings or {})
        self._runs: dict[str, _RunState] = {}
        self._text_sink: SafeTextSink | None = None
        self.versions = {"pydantic_ai": pydantic_ai.__version__}

    def set_text_sink(self, sink: SafeTextSink) -> None:
        self._text_sink = sink

    # -- continuation (persisted by the kernel through the RunStore) ----------
    def snapshot(self, run_id: str) -> dict[str, Any] | None:
        st = self._runs.get(run_id)
        if st is None:
            return None
        return {
            "schema": STATE_SCHEMA,
            "pydantic_ai_version": pydantic_ai.__version__,
            "messages": to_jsonable_python(strip_thinking(st.messages)),
            "pending_reads": dict(st.pending_reads),
            "pending_write": st.pending_write,
            "pending_input": st.pending_input,
            "rejected": dict(st.rejected),
            "tokens": st.tokens,
        }

    def restore(self, run_id: str, state: Mapping[str, Any]) -> None:
        if state.get("schema") != STATE_SCHEMA:
            raise ValueError("unsupported driver continuation schema")
        if state.get("pydantic_ai_version") != pydantic_ai.__version__:
            raise ValueError("driver version changed; continuation cannot resume")
        self._runs[run_id] = _RunState(
            messages=list(ModelMessagesTypeAdapter.validate_python(state["messages"])),
            pending_reads=dict(state["pending_reads"]),
            pending_write=state["pending_write"],
            pending_input=state.get("pending_input"),
            rejected=dict(state["rejected"]),
            tokens=int(state.get("tokens", 0)),
        )

    def tokens_used(self, run_id: str) -> int:
        state = self._runs.get(run_id)
        return state.tokens if state else 0

    # -- driving ----------------------------------------------------------------
    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        st = self._runs.setdefault(ctx.run_id, _RunState())
        results = self._results_for(st, step_input) if st.messages else None
        prompt = step_input.user_input if st.messages else step_input.task
        if st.messages and results is None and step_input.findings:
            prompt = "Host validation feedback: " + json.dumps(
                [
                    {
                        "rule_id": finding.rule_id,
                        "message": finding.message,
                        "expected": finding.expected,
                        "observed": finding.observed,
                    }
                    for finding in step_input.findings
                ],
                ensure_ascii=False,
            )
        first_text = True
        text_filter = _PublicTextFilter()

        async def public_text(_ctx: Any, events: AsyncIterable[AgentStreamEvent]) -> None:
            nonlocal first_text
            async for event in events:
                text = None
                if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                    text = event.part.content
                elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    text = event.delta.content_delta
                if text:
                    text = text_filter.feed(text)
                    if text and self._text_sink is not None:
                        await self._text_sink.emit(ctx, text, new_message=first_text)
                        first_text = False
            tail = text_filter.feed("", final=True)
            if tail and self._text_sink is not None:
                await self._text_sink.emit(ctx, tail, new_message=first_text)

        handler: Any = public_text if self._text_sink is not None else None
        usage = RunUsage()
        try:
            result = await self._agent.run(
                prompt,
                message_history=st.messages or None,
                deferred_tool_results=results,
                toolsets=[self._toolset],
                usage_limits=UsageLimits(
                    request_limit=self._limits.request_limit,
                    total_tokens_limit=max(0, ctx.budgets.max_model_tokens - st.tokens),
                ),
                usage=usage,
                event_stream_handler=handler,
                model_settings=self._settings or None,  # type: ignore[arg-type]
            )
        except UsageLimitExceeded as exc:
            raise DriverBudgetExceeded("model usage limit") from exc
        finally:
            st.tokens += usage.total_tokens
        st.messages = strip_thinking(result.all_messages())
        st.pending_reads, st.pending_write, st.pending_input, st.rejected = {}, None, None, {}
        output = result.output
        if isinstance(output, str):
            return FinalAnswer(text=_public_text(output))
        return self._plan_step(st, output)

    def _results_for(self, st: _RunState, step_input: DriverInput) -> DeferredToolResults | None:
        results = DeferredToolResults()
        observations = {o.request_id: o for o in step_input.observations}
        for call_id in st.pending_reads:
            obs = observations.get(call_id)
            results.calls[call_id] = (
                {"data": dict(obs.data), "evidence_id": obs.evidence.evidence_id}
                if obs is not None
                else {"error": "read was not executed"}
            )
        if st.pending_write is not None:
            if step_input.action_result is not None:
                results.calls[st.pending_write] = dict(step_input.action_result)
            else:
                results.calls[st.pending_write] = {
                    "status": "BLOCKED",
                    "findings": [
                        {
                            "rule_id": f.rule_id,
                            "status": f.status,
                            "message": f.message,
                            "expected": f.expected,
                            "observed": f.observed,
                        }
                        for f in step_input.findings
                    ],
                }
        if st.pending_input is not None:
            results.calls[st.pending_input] = {"user_input": step_input.user_input}
        for call_id, reason in st.rejected.items():
            results.calls[call_id] = {"error": reason}
        return results if results.calls or results.approvals else None

    def _plan_step(self, st: _RunState, requests: DeferredToolRequests) -> DriverStep:
        reads: list[ReadRequest] = []
        writes: list[tuple[str, ToolSpec, dict[str, Any]]] = []
        for call in requests.calls:
            if call.tool_name == "request_clarification":
                question = call.args_as_dict().get("question")
                if (
                    len(requests.calls) == 1
                    and isinstance(question, str)
                    and 0 < len(question.strip()) <= 4000
                ):
                    st.pending_input = call.tool_call_id
                    return AskClarification(question=question.strip())
                st.rejected[call.tool_call_id] = (
                    "ask one clarification separately from business tools"
                )
                continue
            spec = self._tools.get(call.tool_name)
            if spec is None:
                st.rejected[call.tool_call_id] = "unknown tool"
                continue
            args = self._coerced_args(spec, call.args_as_dict())
            if spec.effect is EffectKind.READ:
                st.pending_reads[call.tool_call_id] = spec.contract_id
                reads.append(
                    ReadRequest(
                        request_id=call.tool_call_id,
                        contract_id=spec.contract_id,
                        connection_id=spec.connection_id,
                        arguments=args,
                    )
                )
            else:
                writes.append((call.tool_call_id, spec, args))
        for call in requests.approvals:  # never used for business actions
            st.rejected[call.tool_call_id] = "approval-style tools are not supported"
        if reads:
            for call_id, _, _ in writes:
                st.rejected[call_id] = "read facts first; propose the write in a later step"
            return RequestReads(reads=tuple(reads))
        if writes:
            call_id, spec, args = writes[0]
            for extra_id, _, _ in writes[1:]:
                st.rejected[extra_id] = "only one write may be proposed at a time"
            st.pending_write = call_id
            return ProposeAction(
                proposal=ActionProposal(
                    contract_id=spec.contract_id,
                    connection_id=spec.connection_id,
                    arguments=args,
                    expected_effects=(spec.description,),
                )
            )
        return AskClarification(question="The model made no usable tool request.")

    @staticmethod
    def _coerced_args(spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        props = spec.parameters.get("properties", {})
        return {k: _coerce(v, props.get(k)) for k, v in args.items()}
