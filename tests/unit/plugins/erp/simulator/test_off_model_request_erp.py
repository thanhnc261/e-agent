"""Off mode sends the model exactly today's requests: the ERP draft-po golden (Task 3b.2).

Recorded before any Phase 3 toggle existed (`record_off_model_request_erp`); the notes-pack
golden is asserted by ``tests/unit/adapters/pydantic_ai/test_driver_plan.py``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from .record_off_model_request_erp import GOLDEN, RUNS, assert_matches, record_requests


def _golden() -> dict[str, Any]:
    golden: dict[str, Any] = json.loads(GOLDEN.read_text("utf-8"))
    return golden


async def test_off_model_requests_match_golden() -> None:
    golden = _golden()
    assert tuple(golden) == RUNS
    # The task prompt, the turn after the reads and the acknowledgement turn.
    assert assert_matches(golden, await record_requests()) == 3


def test_off_model_request_golden_fails_on_empty_golden() -> None:
    with pytest.raises(AssertionError, match="0 cases"):
        assert_matches({}, {})
    with pytest.raises(AssertionError, match="0 cases"):
        assert_matches({"erp-draft-po": {"run_state": "SUCCEEDED", "requests": []}}, {})


def test_golden_pins_tools_instructions_and_messages() -> None:
    """A golden without the tool surface or the messages would let a rendering change pass."""
    for name, run in _golden().items():
        assert run["run_state"] == "SUCCEEDED", name
        for request in run["requests"]:
            assert request["function_tools"], name
            assert request["instructions"], name
            assert request["messages"], name
        # The acknowledgement turn carries the verified write's result as a tool return.
        last = run["requests"][-1]["messages"][-1]["parts"]
        assert [p["part_kind"] for p in last] == ["tool-return"], name
        assert last[0]["content"]["status"] == "VERIFIED", name
