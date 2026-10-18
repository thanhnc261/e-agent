"""Off mode is exactly today's behaviour: the notes-domain golden recorded before Phase 2.

ADR 0027. The ERP draft-po golden is asserted by the simulator plugin's tests
(``tests/unit/plugins/erp/simulator/test_off_baseline_erp.py``).
"""

from __future__ import annotations

import json

import pytest

from .record_off_baseline import GOLDEN, RUNS, assert_matches, record_baseline


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
        assert_matches({"notes-write": {"event_types": []}}, {})


def test_golden_records_digests_and_action_states() -> None:
    for name, run in _golden().items():
        assert run["approval_digest"].startswith("jcs-sha256-v1:"), name
        assert [a["state"] for a in run["actions"]] == ["VERIFIED"], name
        assert run["actions"][0]["digest"] == run["approval_digest"], name
