"""Off mode is exactly today's behaviour: the ERP draft-po golden recorded before Phase 2.

ADR 0027. Since Task 3c.2 (ADR 0031 §4, plan D7) the frozen golden is compared through the
projection of the current stream onto its keys, the current stream is recorded beside it
(``golden/off_mode_events_erp_v3.json``), and the frozen golden is proved a projection of
it: same events, order, types, keys and values, plus only ADR 0031 §3's keys. The
notes-domain golden is asserted by the kernel suite (``tests/unit/kernel/test_off_baseline.py``,
``tests/unit/kernel/test_off_projection.py``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from e_agent.contracts.events import RunEventType
from e_agent.kernel.reconstruct import ADDED_KEYS

from .record_off_baseline_erp import (
    GOLDEN,
    GOLDEN_V3,
    RUNS,
    assert_matches,
    phase2_projection,
    record_baseline,
)

PHASE2_SHA256 = "1f01d1ac5bced0114eaf1f9435e63a444d38a8b391040f7622a2c74db8fc2253"
"""The frozen golden's bytes at Task 3c.2's base (``5a728dc``)."""


def _golden() -> dict:  # type: ignore[type-arg]
    return json.loads(GOLDEN.read_text("utf-8"))  # type: ignore[no-any-return]


async def test_off_mode_event_stream_matches_baseline() -> None:
    golden = _golden()
    assert tuple(golden) == RUNS
    assert assert_matches(golden, phase2_projection(await record_baseline())) == len(RUNS)


def test_off_baseline_fails_on_empty_golden() -> None:
    with pytest.raises(AssertionError, match="0 cases"):
        assert_matches({}, {})
    with pytest.raises(AssertionError, match="0 cases"):
        assert_matches({"erp-draft-po": {"event_types": []}}, {})


def test_golden_records_digests_and_action_states() -> None:
    for name, run in _golden().items():
        assert run["approval_digest"].startswith("jcs-sha256-v1:"), name
        assert [a["state"] for a in run["actions"]] == ["VERIFIED"], name
        assert run["actions"][0]["digest"] == run["approval_digest"], name


def test_golden_records_each_events_payload_keys() -> None:
    """A golden without payload key sets would let a payload-only change pass."""
    for name, run in _golden().items():
        keys = run.get("payload_keys")
        assert keys is not None, name
        assert len(keys) == len(run["event_types"]), name
        assert all(isinstance(k, list) and k for k in keys), name


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))  # type: ignore[no-any-return]


def test_phase2_golden_is_frozen() -> None:
    assert hashlib.sha256(GOLDEN.read_bytes()).hexdigest() == PHASE2_SHA256


async def test_off_mode_event_stream_matches_v3() -> None:
    golden = _load(GOLDEN_V3)
    assert tuple(golden) == RUNS
    assert assert_matches(golden, await record_baseline()) == len(RUNS)


def test_phase2_golden_is_a_projection_of_v3() -> None:
    v2, v3 = _load(GOLDEN), _load(GOLDEN_V3)
    assert tuple(v2) == tuple(v3) == RUNS
    assert phase2_projection(v3) == v2
    gained = 0
    for name in RUNS:
        assert v2[name]["event_types"] == v3[name]["event_types"], name
        for event_type, before, after in zip(
            v3[name]["event_types"], v2[name]["payload_keys"], v3[name]["payload_keys"], strict=True
        ):
            extra = set(after) - set(before)
            assert set(before) <= set(after), (name, event_type)
            assert extra <= ADDED_KEYS.get(RunEventType(event_type), frozenset()), extra
            gained += bool(extra)
    print(f"off projection (erp): {len(v3[RUNS[0]]['event_types'])} events, {gained} with keys")
    assert gained > 0


def test_another_difference_fails_the_projection() -> None:
    v2, v3 = _load(GOLDEN), _load(GOLDEN_V3)
    v3[RUNS[0]]["payload_keys"][0].append("data")  # a key ADR 0031 does not list
    assert phase2_projection(v3) != v2
