"""The ``context_assembler: shadow`` consumer over the recorded replay corpus (Task 3d.3).

Every recording replays through the real host, driver and kernel with the run pinned
``shadow``; the run's outcome is the recording's, and every driver turn records
``context.compared``. The check (ADR 0032 §7): no observation whose resource ref the run's
proposal or answer arguments use is left out of a pack or cut by the bound, on any turn.
A "resource ref" is a ``<kind>:<id>`` string, as in ``product:widget-a`` or ``offer:a``; an
observation is about the refs in its data and in its read request's arguments.

This is fixture evidence over recorded model parts (PR-29), and it checks the Phase 3 default
policy (`SHADOW_POLICY`, provisional per plan ruling D3-1..3) against that corpus only.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from e_agent.contracts.context_pack import ContextPolicy
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode
from e_agent.contracts.run import RunState
from e_agent.kernel import context_shadow

from .test_recorded_model_replays import AUTHORED, AUTHORED_ROOT, ROOT, TASKS, replay

RESOURCE_REF = re.compile(r"[a-z][a-z0-9_-]*:\S+")
CASES: list[tuple[Path, str]] = [(ROOT, t) for t in TASKS] + [(AUTHORED_ROOT, t) for t in AUTHORED]


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _strings(item)


def _refs(value: Any) -> set[str]:
    return {s for s in _strings(value) if RESOURCE_REF.fullmatch(s)}


async def _shadow_case(root: Path, task: str) -> tuple[int, int, list[str]]:
    """Replay ``task`` pinned ``shadow``: (referenced observations, comparisons, violations)."""
    runtime, run, recording, cursor, response_count = await replay(
        task, root=root, context_assembler=FeatureMode.SHADOW
    )
    assert run.state is RunState.SUCCEEDED, task  # shadow changes nothing the run acts on
    assert cursor == response_count, task
    writes = runtime.diagnostics()["fixture-erp"]["create_calls"]
    assert writes == recording["expected_fixture_writes"], task
    tenant = runtime.operator.tenant_id
    events = await runtime.store.list_events(tenant, run.run_id)
    compared = [e.payload for e in events if e.type is RunEventType.CONTEXT_COMPARED]
    failed = [e.payload for e in events if e.type is RunEventType.CONTEXT_SHADOW_FAILED]
    cont = await runtime.coordinator._peek_cont(tenant, run.run_id)
    assert not failed, (task, failed)
    assert [p["turn"] for p in compared] == list(range(1, cont.turns + 1)), task

    used = {
        ref
        for e in events
        if e.type is RunEventType.PROPOSAL_CREATED
        for ref in _refs(e.payload["arguments"])
    }
    referenced = {  # by request: the re-read before dispatch gives a request new evidence
        request_id
        for request_id, obs in cont.observations.items()
        if used & (_refs(obs.data) | _refs(cont.reads[request_id].arguments))
    }
    request_of = {
        e.payload["evidence_id"]: e.payload["request_id"]
        for e in events
        if e.type is RunEventType.READ_RECORDED
    }
    violations = [
        f"{task} turn {p['turn']}: {request_of[evidence_id]} {how}"
        for p in compared
        for how, key in (("left out", "omitted_evidence"), ("truncated", "truncated_evidence"))
        for evidence_id in p[key]
        if request_of.get(evidence_id) in referenced
    ]
    return len(referenced), len(compared), violations


async def test_shadow_pack_keeps_referenced_observations() -> None:
    cases = referenced = turns = 0
    violations: list[str] = []
    for root, task in CASES:
        found, compared, wrong = await _shadow_case(root, task)
        cases += 1
        referenced += found
        turns += compared
        violations += wrong
    assert cases == len(TASKS) + len(AUTHORED) == 9, "the replay corpus changed size"
    assert referenced > 0 and turns >= cases, "the check saw nothing it could fail on"
    assert violations == []
    print(f"context shadow: {cases} replays, {turns} turns, {referenced} referenced reads")


async def test_the_check_finds_a_dropped_referenced_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A control: with a bound too small for any observation, the referenced observations
    are left out, and the check above reports them."""
    monkeypatch.setattr(context_shadow, "SHADOW_POLICY", ContextPolicy(max_tool_output_tokens=1))
    referenced, _, violations = await _shadow_case(ROOT, "draft-po")
    assert referenced > 0
    assert violations and all("left out" in v for v in violations)
