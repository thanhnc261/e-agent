"""AgentDriver backed by Pydantic AI 2.x.

Every capability is exposed as an *external* (deferred) tool: the model can only
request calls, and each request comes back to the kernel as DeferredToolRequests.
Reads are executed by the kernel gateway; a write becomes a proposal that goes
through validation, approval, dispatch and verification. Results resume the run
via DeferredToolResults. Nothing effectful executes inside the framework, and
framework approval (`requires_approval`) is never used (ADR 0004).

Continuation hygiene: ThinkingPart content is removed from the stored history
and never leaves the driver (AGENTS.md: no persisted hidden reasoning).

Action plans (Task 2c.9, ADR 0025): a turn offers the deferred ``propose_plan`` tool only
when the kernel passed the run's tool set (``DriverInput.allowed_capabilities``, set only in
execution IR ``on`` for a run bound to its task definition) and the run's effective write
budget (``ctx.budgets.max_admitted_writes``, the value the kernel's plan refusal reads) is
above one. Every other turn sends the model exactly today's tools and instructions
(ENG-TOGGLE-1). A plan call becomes `ProposePlan` and nothing more: each step's connection is
the host's tool spec's, a step that names a connection is refused (PR-11, PR-12), and a
lineage placeholder is built only from the tool's typed ``lineage`` field, so a literal
``$lineage`` key in model arguments stays a literal the plan records refuse. The kernel
validates, approves and dispatches the plan (PR-13).
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import AsyncIterable, Mapping, Sequence
from decimal import Decimal
from typing import Any
from urllib.parse import SplitResult, urlsplit

from e_agent.contracts.capability import EffectKind
from e_agent.contracts.context import TaskContext
from e_agent.contracts.plan import ActionPlan, ActionProposal, LineageRef, PlannedStep
from e_agent.sdk.errors import DriverBudgetExceeded
from e_agent.sdk.ports import (
    AskClarification,
    DriverInput,
    DriverStep,
    FinalAnswer,
    ProposeAction,
    ProposePlan,
    ReadRequest,
    RequestReads,
    SafeTextSink,
)
from pydantic import ValidationError
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

PLAN_TOOL = "propose_plan"
PLAN_INSTRUCTIONS = (
    f"This task may need more than one write. If it does, read the facts first, then call "
    f"{PLAN_TOOL} once with every write as a step, in the order they must run, instead of "
    "calling the write tools. A human approves the whole plan once; the host runs each step "
    "only after the previous one is verified. When a step needs a value from an earlier "
    "step's verified result, name it under that step's lineage, not in its arguments. Never "
    "name a connection. For a single write, call its write tool as usual."
)
"""Added to the instructions only on a turn that offers the plan tool."""
_PLAN_STEP_KEYS = frozenset({"step_id", "tool", "arguments", "depends_on", "lineage"})
_LINEAGE_KEYS = frozenset({"step", "path"})
CONNECTION_REFUSAL = "the host chooses each step's connection; a plan must not name one"
PLAN_SHAPE_REFUSAL = (
    "a plan is a non-empty steps list; each step has a step_id, a tool and an arguments "
    "object, and optionally depends_on (step ids) and lineage"
)
PLAN_TOOL_REFUSAL = "each plan step's tool must be one of the plan's write tools"
PLAN_LINEAGE_REFUSAL = (
    "lineage maps an argument name that is not also in arguments to {step, path}: an "
    "earlier step id and an RFC 6901 JSON pointer into its verified result"
)
PLAN_STRUCTURE_REFUSAL = (
    "the plan's structure is invalid: step ids are unique, each dependency is an earlier "
    "step, and no argument uses the reserved $lineage key"
)
PLAN_REFUSALS = frozenset(
    {
        CONNECTION_REFUSAL,
        PLAN_SHAPE_REFUSAL,
        PLAN_TOOL_REFUSAL,
        PLAN_LINEAGE_REFUSAL,
        PLAN_STRUCTURE_REFUSAL,
    }
)
"""The fixed refusals of a plan call, returned to the model as the call's error."""


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


_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_NO_API_KEY = "not-required"
"""Fixed non-secret key sent when the proxy needs none.

Passing ``None`` would let the OpenAI client read ``OPENAI_API_KEY`` from the process
environment and send an unrelated real key to the proxy (ADR 0021, ADR 0001).
"""


def _malformed_netloc(endpoint: SplitResult) -> bool:
    """A netloc the HTTP client may read differently from urlsplit (bad port, percent escapes)."""
    try:
        endpoint.port  # noqa: B018 - raises ValueError for a non-numeric or out-of-range port
    except ValueError:
        return True
    return "%" in endpoint.netloc


def ollama_model(model_name: str, base_url: str) -> Model:
    endpoint = urlsplit(base_url)
    if (
        _malformed_netloc(endpoint)
        or endpoint.hostname not in _LOOPBACK_HOSTS
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


def litellm_model(model_name: str, base_url: str, api_key: str | None = None) -> Model:
    """LiteLLM proxy on loopback only (ADR 0021); upstream routing is the proxy's configuration."""
    endpoint = urlsplit(base_url)
    if (
        _malformed_netloc(endpoint)
        or endpoint.hostname not in _LOOPBACK_HOSTS
        or endpoint.scheme not in {"http", "https"}
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
        or not model_name
    ):
        raise ValueError("LiteLLM inference requires a loopback proxy endpoint and a model name")
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.litellm import LiteLLMProvider

    provider = LiteLLMProvider(api_base=base_url, api_key=api_key or _NO_API_KEY)
    return OpenAIChatModel(model_name, provider=provider)


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
        allowed = step_input.allowed_capabilities  # the run's tool set (D6); None: all tools
        toolset: Any = (
            self._toolset
            if allowed is None
            else self._toolset.filtered(
                lambda _ctx, tool: (
                    tool.name not in self._tools or self._tools[tool.name].contract_id in allowed
                )
            )
        )
        plan_tool = self._plan_tool(ctx, allowed)
        toolsets: list[Any] = [toolset]
        extra: dict[str, Any] = {}
        if plan_tool is not None:  # `on`, more than one write: offer the plan (Task 2c.9)
            toolsets.append(ExternalToolset([plan_tool]))
            extra["instructions"] = PLAN_INSTRUCTIONS
        usage = RunUsage()
        try:
            result = await self._agent.run(
                prompt,
                message_history=st.messages or None,
                deferred_tool_results=results,
                toolsets=toolsets,
                usage_limits=UsageLimits(
                    request_limit=self._limits.request_limit,
                    total_tokens_limit=max(0, ctx.budgets.max_model_tokens - st.tokens),
                ),
                usage=usage,
                event_stream_handler=handler,
                model_settings=self._settings or None,  # type: ignore[arg-type]
                **extra,
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
        return self._plan_step(st, output, self._plan_step_tools(ctx, allowed))

    def _plan_step_tools(
        self, ctx: TaskContext, allowed: tuple[str, ...] | None
    ) -> tuple[str, ...]:
        """The write tools a plan step may name on this turn; empty when no plan is offered.

        ``allowed`` is None in ``off`` and ``shadow`` (and for a run without a definition),
        so the write budget alone never offers a plan."""
        if allowed is None or ctx.budgets.max_admitted_writes <= 1 or PLAN_TOOL in self._tools:
            return ()
        return tuple(
            sorted(
                spec.name
                for spec in self._tools.values()
                if spec.effect is EffectKind.WRITE and spec.contract_id in allowed
            )
        )

    def _plan_tool(
        self, ctx: TaskContext, allowed: tuple[str, ...] | None
    ) -> ToolDefinition | None:
        names = self._plan_step_tools(ctx, allowed)
        if not names:
            return None
        return ToolDefinition(
            name=PLAN_TOOL,
            description=(
                "Propose several writes as one plan that a human approves once. Steps run in "
                "order, each after the previous one is verified. Each step names a write tool "
                "and its complete arguments; a value copied from an earlier step's verified "
                "result goes under lineage as {step, path}. The host chooses connections. "
                "This grants no approval or authority."
            ),
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": ctx.budgets.max_admitted_writes,
                        "items": {
                            "type": "object",
                            "properties": {
                                "step_id": {"type": "string", "minLength": 1, "maxLength": 64},
                                "tool": {"type": "string", "enum": list(names)},
                                "arguments": {"type": "object"},
                                "depends_on": {"type": "array", "items": {"type": "string"}},
                                "lineage": {
                                    "type": "object",
                                    "description": (
                                        "Argument name to the earlier step and the JSON "
                                        "pointer into its verified result to copy."
                                    ),
                                    "additionalProperties": {
                                        "type": "object",
                                        "properties": {
                                            "step": {"type": "string"},
                                            "path": {"type": "string"},
                                        },
                                        "required": ["step", "path"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["step_id", "tool", "arguments"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["steps"],
                "additionalProperties": False,
            },
        )

    def _results_for(self, st: _RunState, step_input: DriverInput) -> DeferredToolResults | None:
        results = DeferredToolResults()
        observations = {o.request_id: o for o in step_input.observations}
        for call_id in st.pending_reads:
            obs = observations.get(call_id)
            results.calls[call_id] = (
                {"data": dict(obs.data), "evidence_id": obs.evidence.evidence_id}
                if obs is not None
                else {"error": step_input.read_errors.get(call_id, "read was not executed")}
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

    def _plan_step(
        self,
        st: _RunState,
        requests: DeferredToolRequests,
        plan_tools: tuple[str, ...] = (),
    ) -> DriverStep:
        reads: list[ReadRequest] = []
        # A write call (its spec and arguments) or a plan call (spec None, its raw arguments).
        writes: list[tuple[str, ToolSpec | None, dict[str, Any]]] = []
        for call in requests.calls:
            if call.tool_name == PLAN_TOOL and plan_tools:
                writes.append((call.tool_call_id, None, call.args_as_dict()))
                continue
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
            if spec is None:  # the plan call: the turn's one proposal (Task 2c.9)
                plan = self._plan_from_call(args, plan_tools)
                if isinstance(plan, str):
                    st.rejected[call_id] = plan
                    return AskClarification(question="The model made no usable tool request.")
                st.pending_write = call_id
                return ProposePlan(plan=plan)
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

    def _plan_from_call(
        self, args: Mapping[str, Any], plan_tools: tuple[str, ...]
    ) -> ActionPlan | str:
        """The plan a ``propose_plan`` call proposes, or the fixed refusal for the model.

        The checks here only make a refusal precise; the plan records and the kernel are the
        boundary. Each connection is the host's tool spec's. A placeholder is a `LineageRef`
        built from the typed ``lineage`` field; argument values pass through as they came, so
        a literal ``$lineage`` key reaches the records, which refuse it (ADR 0025). The
        kernel assigns the plan id and the task definition (`ProposePlan`)."""
        if set(args) != {"steps"}:
            return _refusal_for_keys(set(args) - {"steps"})
        raw_steps = args["steps"]
        if not isinstance(raw_steps, list) or not raw_steps:
            return PLAN_SHAPE_REFUSAL
        steps: list[PlannedStep] = []
        for raw in raw_steps:
            if not isinstance(raw, dict):
                return PLAN_SHAPE_REFUSAL
            if set(raw) - _PLAN_STEP_KEYS:
                return _refusal_for_keys(set(raw) - _PLAN_STEP_KEYS)
            step_id, tool, arguments = raw.get("step_id"), raw.get("tool"), raw.get("arguments")
            depends_on, lineage = raw.get("depends_on", []), raw.get("lineage", {})
            if not (
                isinstance(step_id, str)
                and step_id
                and isinstance(arguments, dict)
                and isinstance(depends_on, list)
                and all(isinstance(item, str) for item in depends_on)
                and isinstance(lineage, dict)
            ):
                return PLAN_SHAPE_REFUSAL
            spec = self._tools.get(tool) if isinstance(tool, str) else None
            if spec is None or spec.name not in plan_tools:
                return PLAN_TOOL_REFUSAL
            values = self._coerced_args(spec, arguments)
            sources: list[str] = []
            for name, ref in lineage.items():
                if (
                    name in values
                    or not isinstance(ref, dict)
                    or set(ref) != _LINEAGE_KEYS
                    or not all(isinstance(ref[key], str) for key in _LINEAGE_KEYS)
                ):
                    return PLAN_LINEAGE_REFUSAL
                try:
                    values[name] = LineageRef(step_id=ref["step"], path=ref["path"])
                except ValidationError:
                    return PLAN_LINEAGE_REFUSAL
                sources.append(ref["step"])
            try:
                steps.append(
                    PlannedStep(
                        step_id=step_id,
                        proposal=ActionProposal(
                            contract_id=spec.contract_id,
                            connection_id=spec.connection_id,
                            arguments=values,
                            expected_effects=(spec.description,),
                        ),
                        depends_on=tuple(dict.fromkeys([*depends_on, *sources])),
                    )
                )
            except (ValidationError, ValueError):
                return PLAN_STRUCTURE_REFUSAL
        try:
            return ActionPlan(
                plan_id="driver-proposed",
                task_id="driver-proposed",
                task_version="0",
                steps=tuple(steps),
            )
        except (ValidationError, ValueError):
            return PLAN_STRUCTURE_REFUSAL

    @staticmethod
    def _coerced_args(spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        props = spec.parameters.get("properties", {})
        return {k: _coerce(v, props.get(k)) for k, v in args.items()}


def _refusal_for_keys(keys: set[Any]) -> str:
    """A key the plan tool does not define: a connection one gets its own refusal."""
    if any("connection" in str(key).lower() for key in keys):
        return CONNECTION_REFUSAL
    return PLAN_SHAPE_REFUSAL
