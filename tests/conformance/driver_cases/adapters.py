"""The two drivers of the suite, each mapping a case's scenario to its own input.

``pydantic-ai`` replays model responses through a ``FunctionModel``: the captured recordings
in ``tests/replays/erp-model-calls``, the authored grounded recordings in
``tests/replays/erp-authored-grounded-calls`` (their ``<<evidence:CALL_ID>>`` placeholders
resolve to the host's `world.evidence_id`), and a few responses authored here, each named in
`AUTHORED` with what it checks. No model produced an authored response (PR-29). The model
raises when a scenario runs out of responses, so a driver that calls the model more often
than the recording fails the case instead of drifting.

``scripted`` is the ERP scripted driver (`ScriptedErpDriver`): a scenario is its task kind
and mode. It has no model and no continuation, so the cases about what a model receives or
what a snapshot holds are declared not applicable, each with its reason.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from e_agent.adapters.pydantic_ai import PydanticAiDriver
from e_agent.plugins.erp.domain.testing.scripted_tasks import ScriptedErpDriver
from e_agent.sdk.ports import AgentDriver
from pydantic_ai import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    models,
)
from pydantic_ai.messages import ThinkingPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .harness import ModelView, NoContinuation, NoModel
from .world import World, evidence_id

models.ALLOW_MODEL_REQUESTS = False  # the suite never calls a real model

REPLAYS = Path(__file__).resolve().parents[2] / "replays"
CAPTURED = REPLAYS / "erp-model-calls"
GROUNDED = REPLAYS / "erp-authored-grounded-calls"
EVIDENCE = re.compile(r"<<evidence:([^>]+)>>")
SECRET_THINKING = "SECRET-THINKING-PART"
SECRET_TAG = "SECRET-THINK-TAG"


def _recording(path: Path) -> list[ModelResponse]:
    responses = ModelMessagesTypeAdapter.validate_python(json.loads(path.read_text())["responses"])
    assert all(isinstance(r, ModelResponse) for r in responses), path
    return [r for r in responses if isinstance(r, ModelResponse)]


def _call(tool: str, args: Mapping[str, Any], call_id: str) -> ToolCallPart:
    return ToolCallPart(tool, json.dumps(dict(args)), call_id)


def _off_tool() -> list[ModelResponse]:
    """A call to the offers read the shortage tool set leaves out, then the captured
    shortage calls."""
    stray = _call("procurement_offers_read_v1", {"product_ref": "product:widget-a"}, "a-stray")
    return [ModelResponse(parts=[stray]), *_recording(CAPTURED / "shortage.json")]


def _mixed() -> list[ModelResponse]:
    """The captured draft-po reads and its write in one response, then the write again."""
    reads, write, final = _recording(CAPTURED / "draft-po.json")
    call = write.parts[0]
    assert isinstance(call, ToolCallPart)
    early = dataclasses.replace(call, tool_call_id="a-early-write")
    return [ModelResponse(parts=[*reads.parts, early]), write, final]


def _silent() -> list[ModelResponse]:
    """The captured draft-po calls, then a reply of reasoning tags only after the finding."""
    reads, write, _ = _recording(CAPTURED / "draft-po.json")
    return [reads, write, ModelResponse(parts=[TextPart("<think>no idea</think>")])]


def _thinking() -> list[ModelResponse]:
    """The captured draft-po calls with a thinking part beside each tool call and reasoning
    tags in the final text."""
    reads, write, _ = _recording(CAPTURED / "draft-po.json")
    return [
        ModelResponse(parts=[ThinkingPart(SECRET_THINKING), *reads.parts]),
        ModelResponse(parts=[ThinkingPart(SECRET_THINKING), *write.parts]),
        ModelResponse(parts=[TextPart(f"<think>{SECRET_TAG}</think>Created the draft PO.")]),
    ]


def _twice(path: Path) -> list[ModelResponse]:
    """A recording's responses for two runs that take turns: each response twice."""
    return [copy.deepcopy(r) for r in _recording(path) for _ in range(2)]


def _thrice(path: Path, count: int) -> list[ModelResponse]:
    """The first ``count`` responses of a recording, for three runs one after another."""
    head = _recording(path)[:count]
    return [copy.deepcopy(r) for _ in range(3) for r in head]


SCENARIOS: dict[str, Callable[[], list[ModelResponse]]] = {
    "draft-po": lambda: _recording(CAPTURED / "draft-po.json"),
    "shortage": lambda: _recording(CAPTURED / "shortage.json"),
    "shortage-off-tool": _off_tool,
    "shortage-cited": lambda: _recording(GROUNDED / "shortage-cited.json"),
    "shortage-cited-thrice": lambda: _thrice(GROUNDED / "shortage-cited.json", 2),
    "draft-po-rationale": lambda: _recording(GROUNDED / "draft-po-rationale.json"),
    "draft-po-repair": lambda: _recording(GROUNDED / "draft-po-misruled.json"),
    "draft-po-repair-twice": lambda: _twice(GROUNDED / "draft-po-misruled.json"),
    "mixed": _mixed,
    "repair-silent": _silent,
    "thinking": _thinking,
}
AUTHORED = {
    "shortage-off-tool": _off_tool.__doc__,
    "mixed": _mixed.__doc__,
    "repair-silent": _silent.__doc__,
    "thinking": _thinking.__doc__,
}
"""The responses authored in this suite, beside the recordings they extend."""


def _resume(old: AgentDriver, new: AgentDriver, run_ids: tuple[str, ...]) -> AgentDriver:
    """``new`` resumed from ``old`` as the kernel resumes it (`_restore_for_turn`): a JSON
    round trip of each run's snapshot when the driver has both methods, else fresh."""
    snapshot = getattr(old, "snapshot", None)
    restore = getattr(new, "restore", None)
    if snapshot is None or restore is None:
        return new
    for run_id in run_ids:
        state = snapshot(run_id)
        if state is not None:
            restore(run_id, json.loads(json.dumps(state)))
    return new


def _snapshot(driver: AgentDriver, run_id: str) -> dict[str, Any] | None:
    snapshot = getattr(driver, "snapshot", None)
    if snapshot is None:
        raise NoContinuation(f"{driver.driver_id} has no snapshot")
    state: dict[str, Any] | None = snapshot(run_id)
    return state


class _Script:
    """A ``FunctionModel`` callback: answers with the scenario's responses in order and
    records each request's view."""

    def __init__(self, responses: list[ModelResponse], names: Mapping[str, str]) -> None:
        self.responses = copy.deepcopy(responses)
        self.names = names
        self.views: list[ModelView] = []

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.views.append(_view(messages, info, self.names))
        if len(self.views) > len(self.responses):
            raise AssertionError("the driver asked for more model responses than recorded")
        response = self.responses[len(self.views) - 1]
        for part in response.parts:
            if isinstance(part, ToolCallPart) and isinstance(part.args, str):
                part.args = EVIDENCE.sub(lambda m: evidence_id(m.group(1)), part.args)
        return response


def _view(messages: list[ModelMessage], info: AgentInfo, names: Mapping[str, str]) -> ModelView:
    tools = info.function_tools
    calls = tuple(
        p.tool_call_id
        for m in messages
        if isinstance(m, ModelResponse)
        for p in m.parts
        if isinstance(p, ToolCallPart)
    )
    returns = {
        p.tool_call_id: p.content
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    }
    prompts = tuple(
        str(p.content)
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, UserPromptPart)
    )
    sent = json.dumps(
        {
            "instructions": info.instructions,
            "tools": [dataclasses.asdict(t) for t in tools],
            "messages": ModelMessagesTypeAdapter.dump_python(messages, mode="json"),
        },
        ensure_ascii=False,
        default=str,
    )
    return ModelView(
        instructions=info.instructions or "",
        offered=frozenset(names[t.name] for t in tools if t.name in names),
        protocol_tools=frozenset(t.name for t in tools if t.name not in names),
        schemas={names.get(t.name, t.name): t.parameters_json_schema for t in tools},
        call_ids=calls,
        return_ids=tuple(returns),
        returns=returns,
        prompts=prompts,
        sent=sent,
    )


@dataclasses.dataclass
class PydanticSubject:
    world: World
    script: _Script
    driver: AgentDriver = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        self.driver = self._new()

    @property
    def connection_id(self) -> str:
        return self.world.connection_id

    def _new(self) -> PydanticAiDriver:
        return PydanticAiDriver(
            FunctionModel(self.script), self.world.specs, guidance=self.world.guidance
        )

    def views(self) -> list[ModelView]:
        return list(self.script.views)

    def restart(self, *run_ids: str) -> None:
        self.driver = _resume(self.driver, self._new(), run_ids)

    def snapshot(self, run_id: str) -> dict[str, Any] | None:
        return _snapshot(self.driver, run_id)


@dataclasses.dataclass
class PydanticAdapter:
    world: World
    name: str = "pydantic-ai"
    not_applicable: Mapping[str, str] = dataclasses.field(default_factory=dict)

    def subject(self, scenario: str) -> PydanticSubject:
        names = {spec.name: spec.contract_id for spec in self.world.specs}
        return PydanticSubject(self.world, _Script(SCENARIOS[scenario](), names))


SCRIPTED: dict[str, tuple[str, str]] = {
    "draft-po": ("draft-po", "valid"),
    "shortage": ("shortage", "valid"),
    "shortage-off-tool": ("shortage", "valid"),
    "shortage-cited": ("shortage", "valid"),
    "shortage-cited-thrice": ("shortage", "valid"),
    "draft-po-rationale": ("draft-po", "valid"),
    "draft-po-repair": ("draft-po", "invalid-then-repair"),
    "draft-po-repair-twice": ("draft-po", "invalid-then-repair"),
}
"""Scenario to the scripted driver's task kind and mode."""

NO_MODEL = "no model: it offers no tools and sends no model request"
NO_HISTORY = "keeps no call and return history: each step is computed from DriverInput alone"
SCRIPTED_NOT_APPLICABLE = {
    "tools.offered_equals_allowed": (
        f"{NO_MODEL}; the calls it makes are checked by tools.calls_within_allowed"
    ),
    "deferred.mixed_turn_defers_write": (
        "no model: its fixed code never asks for reads and a write in one step"
    ),
    "resume.rendering_marker": (
        "declares neither snapshot nor restore: the kernel starts it fresh at its next turn "
        "(continuation._restore_for_turn), so it has no snapshot to mark"
    ),
    "pack.stable_prefix_unchanged": f"{NO_MODEL}, so it renders no stable prefix",
    "clearing.keeps_call_return_pairs": NO_HISTORY,
    "clearing.not_while_pending": NO_HISTORY,
    "findings.in_suffix_not_history": f"{NO_MODEL}, and it persists no history",
    "repair.never_silent": "no model reply: each of its answers is a fixed, non-empty text",
    "budget.tokens_respected": "makes no model call, so it spends no model tokens",
    "hygiene.no_hidden_reasoning": "no model: it produces no reasoning and persists nothing",
}


@dataclasses.dataclass
class ScriptedSubject:
    world: World
    task_kind: str
    mode: str
    driver: AgentDriver = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        self.driver = self._new()

    @property
    def connection_id(self) -> str:
        return self.world.connection_id

    def _new(self) -> ScriptedErpDriver:
        return ScriptedErpDriver(
            connection_id=self.world.connection_id, mode=self.mode, task_kind=self.task_kind
        )

    def views(self) -> list[ModelView]:
        raise NoModel("the scripted driver has no model")

    def restart(self, *run_ids: str) -> None:
        self.driver = _resume(self.driver, self._new(), run_ids)

    def snapshot(self, run_id: str) -> dict[str, Any] | None:
        return _snapshot(self.driver, run_id)


@dataclasses.dataclass
class ScriptedAdapter:
    world: World
    name: str = "scripted"
    not_applicable: Mapping[str, str] = dataclasses.field(
        default_factory=lambda: dict(SCRIPTED_NOT_APPLICABLE)
    )

    def subject(self, scenario: str) -> ScriptedSubject:
        task_kind, mode = SCRIPTED[scenario]
        return ScriptedSubject(self.world, task_kind, mode)


ADAPTERS: dict[str, Callable[[World], Any]] = {
    "pydantic-ai": PydanticAdapter,
    "scripted": ScriptedAdapter,
}
NOT_APPLICABLE: dict[str, Mapping[str, str]] = {
    "pydantic-ai": {},
    "scripted": SCRIPTED_NOT_APPLICABLE,
}
"""What each adapter declares not applicable, by driver name."""
