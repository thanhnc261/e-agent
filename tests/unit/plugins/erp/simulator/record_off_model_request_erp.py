"""Record the ``off`` model requests of the ERP draft-po run (Task 3b.2, ADR 0032).

The ERP counterpart of the notes-pack golden
(``tests/unit/adapters/pydantic_ai/golden/off_model_request.json``): every model request
the pydantic-ai driver builds for the simulator's fixture profile, with all Phase 3 toggles
``off``, recorded on the code as Task 3b.1 left it, before any Phase 3 toggle existed.

The run replays the captured draft-po model parts
(``tests/replays/erp-model-calls/draft-po.json``) through a ``FunctionModel``, so no network
and no model is used. The driver is built from the registry as `build_driver` builds it
(`tool_specs`, the admitted guidance). Each request records what the driver decides (the
function and output tools, whether text output is allowed, the instructions) and the
messages the model receives: the task prompt, the tool returns rendered from observations
and the acknowledgement turn after the verified write. Timestamps are dropped, and generated
ids are normalised to ``<prefix>#<ordinal of first appearance>`` under the counter-based
``new_id`` of the event baseline (`record_off_baseline_erp.deterministic_ids`).

Phase 3 must leave this golden unchanged in ``off`` (Tasks 3b.3, 3d.4, 3e.4). Re-record
only for a change the plan names:
``uv run python tests/unit/plugins/erp/simulator/record_off_model_request_erp.py``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Any

from e_agent.adapters.pydantic_ai import PydanticAiDriver
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.run import RunState
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.bootstrap import build_runtime, tool_specs
from e_agent.server.profile import load_profile
from pydantic_ai import ModelMessage, ModelMessagesTypeAdapter, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .record_off_baseline_erp import _normalise, deterministic_ids

GOLDEN = Path(__file__).parent / "golden" / "off_model_request_erp.json"
REPLAY = Path(__file__).resolve().parents[5] / "tests/replays/erp-model-calls/draft-po.json"
RUNS = ("erp-draft-po",)


PER_CALL_IDS = ("run_id", "conversation_id")
"""pydantic-ai's own per-call ids (uuid7, time-based), replaced by ``<key>#<ordinal>``."""


def _strip(value: Any, seen: dict[str, str]) -> Any:
    """Drop timestamps and normalise generated ids, recursively."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if k == "timestamp":
                continue
            if k in PER_CALL_IDS and isinstance(v, str):
                key = f"{k}:{v}"
                if key not in seen:
                    seen[key] = f"{k}#{sum(1 for s in seen if s.startswith(k + ':')) + 1}"
                out[k] = seen[key]
                continue
            out[k] = _strip(v, seen)
        return out
    if isinstance(value, list):
        return [_strip(v, seen) for v in value]
    if isinstance(value, str):
        return _normalise(value, seen)
    return value


def _request_view(messages: list[ModelMessage], info: AgentInfo) -> dict[str, Any]:
    return {
        "function_tools": [dataclasses.asdict(t) for t in info.function_tools],
        "output_tools": [dataclasses.asdict(t) for t in info.output_tools],
        "allow_text_output": info.allow_text_output,
        "instructions": info.instructions,
        "messages": ModelMessagesTypeAdapter.dump_python(messages, mode="json"),
    }


async def erp_draft_po_requests() -> dict[str, Any]:
    """The ERP draft-po run on the fixture profile, replayed and approved: every request."""
    recording = json.loads(REPLAY.read_text("utf-8"))
    responses = ModelMessagesTypeAdapter.validate_python(recording["responses"])
    seen_requests: list[dict[str, Any]] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen_requests.append(_request_view(messages, info))
        if len(seen_requests) > len(responses):
            raise AssertionError("the draft-po replay asked for more model responses")
        response = responses[len(seen_requests) - 1]
        assert isinstance(response, ModelResponse)
        return response

    with deterministic_ids():
        profile = load_profile(fixture_profile_path())
        rt = await build_runtime(
            profile,
            driver_factory=lambda registry: PydanticAiDriver(
                FunctionModel(respond),
                tool_specs(registry, profile),
                guidance=registry.agent_guidance,
                requests_per_step=profile.driver.requests_per_step,
            ),
        )
        run = await rt.coordinator.start_run(rt.operator, recording["prompt"], rt.scope)
        assert run.state is RunState.WAITING_APPROVAL, run.state
        pres = await rt.coordinator.pending_approval(rt.operator.tenant_id, run.run_id)
        run = await rt.coordinator.decide(
            actor=rt.operator,
            run_id=run.run_id,
            action_id=pres.action_id,
            action_digest=pres.digest,
            expected_run_revision=pres.run_revision,
            decision=ApprovalDecision.APPROVED,
        )
        assert run.state is RunState.SUCCEEDED, run.state
    seen: dict[str, str] = {}
    return {"run_state": str(run.state), "requests": _strip(seen_requests, seen)}


async def record_requests() -> dict[str, Any]:
    return {"erp-draft-po": await erp_draft_po_requests()}


def assert_matches(golden: dict[str, Any], actual: dict[str, Any]) -> int:
    """Compare every recorded request; refuse a golden with no runs or no requests
    (ENG-EVID-4, PR-31). Returns the number of requests compared."""
    cases = [(name, i) for name, run in golden.items() for i in range(len(run.get("requests", [])))]
    if not cases or any(not run.get("requests") for run in golden.values()):
        raise AssertionError(f"off model-request golden has {len(cases)} cases; refusing")
    assert set(actual) == set(golden), "off model-request runs differ from the golden"
    for name, run in golden.items():
        got = actual[name]
        assert got["run_state"] == run["run_state"], f"run state changed for {name}"
        assert len(got["requests"]) == len(run["requests"]), f"request count changed for {name}"
        for i, request in enumerate(run["requests"]):
            assert json.dumps(got["requests"][i], sort_keys=True) == json.dumps(
                request, sort_keys=True
            ), f"model request {i} changed for {name}"
    print(f"off model-request golden: {len(cases)} requests matched")
    return len(cases)


def main() -> None:
    requests = asyncio.run(record_requests())
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(requests, indent=2, ensure_ascii=False) + "\n", "utf-8")
    count = sum(len(run["requests"]) for run in requests.values())
    print(f"wrote {GOLDEN} ({len(requests)} runs, {count} requests)")


if __name__ == "__main__":
    main()
