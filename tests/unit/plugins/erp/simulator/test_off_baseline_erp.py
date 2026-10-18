"""Off mode is exactly today's behaviour: the ERP draft-po golden recorded before Phase 2.

ADR 0027. The notes-domain golden is asserted by the kernel suite
(``tests/unit/kernel/test_off_baseline.py``).
"""

from __future__ import annotations

import json

import pytest

from .record_off_baseline_erp import GOLDEN, RUNS, assert_matches, record_baseline


def _golden() -> dict:  # type: ignore[type-arg]
    return json.loads(GOLDEN.read_text("utf-8"))  # type: ignore[no-any-return]


async def test_off_baseline_matches_golden() -> None:
    golden = _golden()
    assert tuple(golden) == RUNS
    assert assert_matches(golden, await record_baseline()) == len(RUNS)


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
