"""Record the model requests of a pack-rendered notes run (Task 3d.4, ADR 0032 §6).

The `on` counterpart of ``golden/off_model_request.json``: the pydantic-ai driver gets a
``ContextPack`` on every turn (``DriverInput.context``), as the kernel will pass it under
``context_assembler: on`` (Task 3d.5). Each pack is built by the kernel's ``assemble`` on a
local route, so the golden re-records whenever ``kernel/context.py`` changes its rendering.

The run has four turns: the task (the model asks for a read), the read's return (the model
proposes a write), the write blocked with a finding (the model proposes again) and the
acknowledgement after the verified write. Each request records what the driver decides (the
function and output tools, whether text output is allowed, the instructions) and every
message the model receives. Timestamps are dropped and pydantic-ai's per-call ``run_id`` and
``conversation_id`` are normalised to ``<key>#<ordinal>``. No network and no model is used.

Re-record only for a change the plan names:
``uv run python tests/unit/adapters/pydantic_ai/record_on_model_request.py``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from e_agent.adapters.pydantic_ai import PydanticAiDriver, ToolSpec
from e_agent.contracts.capability import EffectKind
from e_agent.contracts.context import Budgets, Principal, TaskContext
from e_agent.contracts.context_pack import ContextPack, ContextPolicy
from e_agent.contracts.data_classes import DataClass
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.progress import BudgetsUsed, ProgressLedger, TaskRefState
from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.kernel.context import assemble
from e_agent.sdk.ports import DriverInput, FinalAnswer, Observation, ProposeAction, RequestReads
from pydantic_ai import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    TextPart,
    ToolCallPart,
    models,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

models.ALLOW_MODEL_REQUESTS = False  # CI never calls a real model

GOLDEN = Path(__file__).parent / "golden" / "on_model_request.json"
RUNS = ("notes-on",)
GUIDANCE = ("Domain guidance: write notes briefly.",)
NOW = datetime(2026, 10, 19, tzinfo=UTC)

LOCAL = {"data_boundary": "local", "data_boundary_basis": "verified"}
UNDECLARED = {
    "data_boundary": "hosted:unknown",
    "data_boundary_basis": "default",
    "data_processing_declared": False,
}


def _spec(contract_id: str, effect: EffectKind) -> ToolSpec:
    return ToolSpec(
        contract_id=contract_id,
        effect=effect,
        description=f"{contract_id} tool",
        parameters={
            "type": "object",
            "properties": {"note_ref": {"type": "string"}, "text": {"type": "string"}},
        },
        connection_id="conn-host",
    )


READ = _spec("notes.note.read.v1", EffectKind.READ)
WRITE = _spec("notes.note.create.v1", EffectKind.WRITE)
SPECS = (READ, WRITE)
TOOL_SET = (READ.contract_id, WRITE.contract_id)
CLASSES: dict[str, dict[str, DataClass]] = {
    READ.contract_id: {
        "/output/notes/items/note_ref": DataClass.INTERNAL,
        "/output/notes/items/text": DataClass.INTERNAL,
        "/output/notes/items/count": DataClass.INTERNAL,
        "/output/notes/items/author": DataClass.PERSONAL,
    }
}


def classes(contract_id: str) -> Mapping[str, DataClass]:
    return CLASSES.get(contract_id, {})


def ctx(run_id: str) -> TaskContext:
    return TaskContext(
        run_id=run_id,
        tenant_id="t",
        principal=Principal(principal_id="p", tenant_id="t", roles=frozenset()),
        resource_scope=frozenset({"conn-host"}),
        deadline=datetime(2030, 1, 1, tzinfo=UTC),
        budgets=Budgets(),
    )


def evidence(request_id: str) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=f"ev-{request_id}",
        tenant_id="t",
        source="fixture",
        locator=f"loc:{request_id}",
        revision="1",
        observed_at=NOW,
        scope="tenant",
    )


def observation(request_id: str, data: Mapping[str, Any]) -> Observation:
    return Observation(
        request_id=request_id,
        contract_id=READ.contract_id,
        data=data,
        evidence=evidence(request_id),
    )


def ledger(turns: int = 1) -> ProgressLedger:
    return ProgressLedger(
        run_id="run-1",
        goal="Write a note about the standup",
        task_ref=None,
        task_ref_state=TaskRefState.NONE,
        facts=(),
        done=(),
        pending=(),
        open_findings=(),
        rules_evaluated=(),
        repair_turns=(),
        budgets_used=BudgetsUsed(
            reads_recorded=0,
            failed_validations=0,
            admitted_writes=0,
            driver_turns=turns,
            model_tokens="unknown",
        ),
    )


def finding(
    *, message: str = "the note text is too long", observed: str | None = "212 characters"
) -> Finding:
    return Finding(
        rule_id="NOTE-001",
        rule_version="1",
        status=ValidationStatus.FAIL,
        message=message,
        expected="at most 200 characters",
        observed=observed,
    )


def pack(
    observations: Sequence[Observation] = (),
    *,
    route: Mapping[str, Any] = LOCAL,
    findings: Sequence[Finding] = (),
    read_errors: Mapping[str, str] | None = None,
    turn: int | None = None,
    observation_turns: Mapping[str, int] | None = None,
    deferred_pending: bool = False,
    turns: int = 1,
) -> ContextPack:
    """The pack the kernel's assembler builds for one turn of the notes run."""
    return assemble(
        ContextPolicy(),
        ledger(turns),
        observations,
        read_errors or {},
        findings,
        classes,
        route,
        tool_set=TOOL_SET,
        turn=turn,
        observation_turns=observation_turns or {},
        deferred_pending=deferred_pending,
    )


class Script:
    """A ``FunctionModel`` that answers with the given responses in order and records what
    each request sent: the messages and the request view."""

    def __init__(self, responses: Sequence[ModelResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[list[ModelMessage]] = []
        self.infos: list[AgentInfo] = []

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.requests.append(list(messages))
        self.infos.append(info)
        if len(self.requests) > len(self.responses):
            raise AssertionError("the script asked for more model responses")
        return self.responses[len(self.requests) - 1]

    def driver(self, specs: Sequence[ToolSpec] = SPECS) -> PydanticAiDriver:
        return PydanticAiDriver(FunctionModel(self), specs, guidance=GUIDANCE)

    def sent(self, index: int = -1) -> str:
        """Everything request ``index`` sent: its messages and its instructions, as JSON."""
        return json.dumps(
            {
                "messages": ModelMessagesTypeAdapter.dump_python(self.requests[index], mode="json"),
                "instructions": self.infos[index].instructions,
            },
            ensure_ascii=False,
        )


def call(tool: ToolSpec, args: Mapping[str, Any], call_id: str) -> ToolCallPart:
    return ToolCallPart(tool.name, dict(args), call_id)


PER_CALL_IDS = ("run_id", "conversation_id")


def _strip(value: Any, seen: dict[str, str]) -> Any:
    """Drop timestamps and normalise pydantic-ai's per-call ids, recursively."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if k == "timestamp":
                continue
            if k in PER_CALL_IDS and isinstance(v, str):
                key = f"{k}:{v}"
                if key not in seen:
                    ordinal = sum(1 for s in seen if s.startswith(k + ":")) + 1
                    seen[key] = f"{k}#{ordinal}"
                out[k] = seen[key]
                continue
            out[k] = _strip(v, seen)
        return out
    if isinstance(value, list):
        return [_strip(v, seen) for v in value]
    return value


def request_view(messages: list[ModelMessage], info: AgentInfo) -> dict[str, Any]:
    return {
        "function_tools": [dataclasses.asdict(t) for t in info.function_tools],
        "output_tools": [dataclasses.asdict(t) for t in info.output_tools],
        "allow_text_output": info.allow_text_output,
        "instructions": info.instructions,
        "messages": ModelMessagesTypeAdapter.dump_python(messages, mode="json"),
    }


NOTE = {"notes": [{"note_ref": "note:1", "text": "standup at <9> & later", "count": 3}]}


async def notes_on_requests() -> dict[str, Any]:
    """The four-turn notes run, every turn rendered from a pack: every request."""
    script = Script(
        [
            ModelResponse(parts=[call(READ, {"note_ref": "note:1"}, "c1")]),
            ModelResponse(parts=[call(WRITE, {"text": "x" * 212}, "w1")]),
            ModelResponse(parts=[call(WRITE, {"text": "standup moved"}, "w2")]),
            ModelResponse(parts=[TextPart("Created the note.")]),
        ]
    )
    driver = script.driver()
    run = ctx("golden_on")
    note = observation("c1", NOTE)
    step = await driver.advance(run, DriverInput(task="Write a note", context=pack()))
    assert isinstance(step, RequestReads), step
    step = await driver.advance(
        run,
        DriverInput(task="Write a note", observations=(note,), context=pack((note,), turn=1)),
    )
    assert isinstance(step, ProposeAction), step
    blocked = (finding(),)
    step = await driver.advance(
        run,
        DriverInput(
            task="Write a note",
            observations=(note,),
            findings=blocked,
            context=pack((note,), findings=blocked, turn=2, deferred_pending=True, turns=2),
        ),
    )
    assert isinstance(step, ProposeAction), step
    step = await driver.advance(
        run,
        DriverInput(
            task="Write a note",
            observations=(note,),
            action_result={"status": "VERIFIED", "external_refs": ["note:2"]},
            context=pack((note,), turn=3, turns=3),
        ),
    )
    assert isinstance(step, FinalAnswer), step
    views = [request_view(m, i) for m, i in zip(script.requests, script.infos, strict=True)]
    snapshot = driver.snapshot(run.run_id)
    assert snapshot is not None
    return {
        "rendering": snapshot.get("rendering"),
        "requests": _strip(views, {}),
    }


async def record_requests() -> dict[str, Any]:
    return {"notes-on": await notes_on_requests()}


def assert_matches(
    golden: Mapping[str, Any], actual: Mapping[str, Any], *, out: Callable[[str], None] = print
) -> int:
    """Compare every recorded request; refuse a golden with no runs or no requests
    (ENG-EVID-4, PR-31). Returns the number of requests compared."""
    cases = [(name, i) for name, run in golden.items() for i in range(len(run.get("requests", [])))]
    if not cases or any(not run.get("requests") for run in golden.values()):
        raise AssertionError(f"on model-request golden has {len(cases)} cases; refusing")
    assert set(actual) == set(golden), "on model-request runs differ from the golden"
    for name, run in golden.items():
        got = actual[name]
        assert got["rendering"] == run["rendering"], f"snapshot marker changed for {name}"
        assert len(got["requests"]) == len(run["requests"]), f"request count changed for {name}"
        for i, request in enumerate(run["requests"]):
            assert json.dumps(got["requests"][i], sort_keys=True) == json.dumps(
                request, sort_keys=True
            ), f"model request {i} changed for {name}"
    out(f"on model-request golden: {len(cases)} requests matched")
    return len(cases)


def main() -> None:
    requests = asyncio.run(record_requests())
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(requests, indent=2, ensure_ascii=False) + "\n", "utf-8")
    count = sum(len(run["requests"]) for run in requests.values())
    print(f"wrote {GOLDEN} ({len(requests)} runs, {count} requests)")


if __name__ == "__main__":
    main()
