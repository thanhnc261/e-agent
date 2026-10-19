"""The ``off`` proof refined for the reconstruction keys (ADR 0031 §4, plan D7, Task 3c.2).

The Phase 2 golden (``golden/off_mode_events.json``) is frozen. The current ``off`` stream is
recorded beside it as ``golden/off_mode_events_v3.json``, and the frozen golden must be a
projection of it: the same events in the same order with the same types, keys and values,
plus only the keys ADR 0031 §3 lists. Any other difference fails. The ERP counterpart is in
``tests/unit/plugins/erp/simulator/test_off_baseline_erp.py``.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import pytest
from e_agent.contracts.events import RunEventType
from e_agent.kernel.reconstruct import ADDED_KEYS

from .record_off_baseline import (
    GOLDEN,
    GOLDEN_V3,
    RUNS,
    assert_matches,
    phase2_projection,
    record_baseline,
)

PHASE2_SHA256 = "01790ebfcc042ed6b6037017e9ced74e2e50db4b51eef638abc2f7eab8304f97"
"""The frozen golden's bytes at Task 3c.2's base (``5a728dc``)."""

ADR_0031_KEYS = {
    "run.created": {
        "requester_id",
        "logical_operation_id",
        "created_at",
        "task_id",
        "task_version",
    },
    "run.state_changed": {"from", "to", "reason", "reason_code", "blocked_action_ids"},
    "proposal.created": {
        "binding_id",
        "connection_id",
        "connection_version",
        "credential_subject",
        "credential_version",
        "digest",
        "logical_operation_id",
        "plan_id",
        "step_index",
        "evidence_ids",
    },
    "validation.completed": {"action_state"},
    "approval.requested": {"plan_id", "step_index"},
    "approval.decided": {"approval_id", "policy_version", "issued_at", "expires_at"},
    "outcome.reported": {"action_state"},
}
"""ADR 0031 §3's table, written out here so the kernel's list cannot drift from it."""


def _load(path: Any) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))  # type: ignore[no-any-return]


def test_added_keys_are_the_adr_0031_table() -> None:
    assert {str(t): set(keys) for t, keys in ADDED_KEYS.items()} == ADR_0031_KEYS


def test_phase2_golden_is_frozen() -> None:
    assert hashlib.sha256(GOLDEN.read_bytes()).hexdigest() == PHASE2_SHA256


async def test_off_mode_event_stream_matches_v3() -> None:
    golden = _load(GOLDEN_V3)
    assert tuple(golden) == RUNS
    assert assert_matches(golden, await record_baseline()) == len(RUNS)


def _added(v2: dict[str, Any], v3: dict[str, Any]) -> int:
    """Per event: the Phase 2 keys are kept and only §3 keys are added; the count of
    events that gained a key."""
    gained = 0
    for name in v2:
        old, new = v2[name], v3[name]
        assert old["event_types"] == new["event_types"], name
        for event_type, before, after in zip(
            new["event_types"], old["payload_keys"], new["payload_keys"], strict=True
        ):
            assert set(before) <= set(after), (name, event_type)
            extra = set(after) - set(before)
            assert extra <= ADDED_KEYS.get(RunEventType(event_type), frozenset()), extra
            gained += bool(extra)
    return gained


def test_phase2_golden_is_a_projection_of_v3() -> None:
    v2, v3 = _load(GOLDEN), _load(GOLDEN_V3)
    assert tuple(v2) == tuple(v3) == RUNS
    assert phase2_projection(v3) == v2
    gained = _added(v2, v3)
    print(
        f"off projection: {sum(len(r['event_types']) for r in v3.values())} events, "
        f"{gained} with ADR 0031 keys"
    )
    assert gained > 0  # the v3 golden records the new keys


@pytest.mark.parametrize(
    "change",
    ["extra key", "dropped key", "reordered events", "changed digest", "changed state"],
)
def test_any_other_difference_fails_the_projection(change: str) -> None:
    v2, v3 = _load(GOLDEN), copy.deepcopy(_load(GOLDEN_V3))
    run = v3[RUNS[0]]
    read = run["event_types"].index("read.recorded")
    if change == "extra key":
        run["payload_keys"][read].append("data")
    elif change == "dropped key":
        run["payload_keys"][read].pop()
    elif change == "reordered events":
        run["event_types"][0], run["event_types"][1] = run["event_types"][1], run["event_types"][0]
        run["payload_keys"][0], run["payload_keys"][1] = (
            run["payload_keys"][1],
            run["payload_keys"][0],
        )
    elif change == "changed digest":
        run["approval_digest"] = "jcs-sha256-v1:0"
    else:
        run["actions"][0]["state"] = "BLOCKED"
    assert phase2_projection(v3) != v2
