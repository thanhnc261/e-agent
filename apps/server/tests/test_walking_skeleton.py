"""End-to-end walking skeleton (I02 exit): fixture driver + fake ERP + real kernel + CLI."""

import json

import pytest
from e_agent.server.cli import main


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> dict:  # type: ignore[type-arg]
    code = main(["demo", "--json", *args])
    assert code == 0
    return json.loads(capsys.readouterr().out)  # type: ignore[no-any-return]


def _types(result: dict) -> list[str]:  # type: ignore[type-arg]
    return [e["type"] for e in result["events"]]


def test_valid_request_creates_exactly_one_verified_draft(capsys) -> None:  # type: ignore[no-untyped-def]
    result = _run(capsys, "--approve")
    assert result["environment"] == "fixture"
    assert result["run"]["state"] == "SUCCEEDED"
    assert result["fixture_erp_create_calls"] == 1
    outcome = next(e for e in result["events"] if e["type"] == "outcome.reported")
    assert outcome["payload"]["status"] == "VERIFIED"


def test_invalid_proposal_is_blocked_then_repaired(capsys) -> None:  # type: ignore[no-untyped-def]
    result = _run(capsys, "--driver-mode", "invalid-then-repair", "--approve")
    validations = [e["payload"] for e in result["events"] if e["type"] == "validation.completed"]
    assert validations[0]["status"] == "FAIL"
    failed = {f["rule_id"] for f in validations[0]["findings"] if f["status"] == "FAIL"}
    assert "PR-003" in failed
    assert validations[1]["status"] == "PASS"
    assert result["run"]["state"] == "SUCCEEDED"


def test_no_decision_leaves_run_waiting(capsys) -> None:  # type: ignore[no-untyped-def]
    result = _run(capsys)
    assert result["run"]["state"] == "WAITING_APPROVAL"
    assert result["fixture_erp_create_calls"] == 0


def test_rejection_creates_nothing(capsys) -> None:  # type: ignore[no-untyped-def]
    result = _run(capsys, "--reject")
    assert result["run"]["state"] == "FAILED"
    assert result["fixture_erp_create_calls"] == 0


def test_zero_shortage_is_a_verified_no_op(capsys) -> None:  # type: ignore[no-untyped-def]
    result = _run(capsys, "--scenario", "zero-shortage")
    assert result["run"]["state"] == "SUCCEEDED"
    assert "proposal.created" not in _types(result)


def test_over_budget_is_blocked(capsys) -> None:  # type: ignore[no-untyped-def]
    result = _run(capsys, "--scenario", "over-budget", "--approve")
    assert result["run"]["state"] == "FAILED"
    assert result["fixture_erp_create_calls"] == 0


def test_lost_response_is_unknown_until_reconciled(capsys) -> None:  # type: ignore[no-untyped-def]
    pending = _run(capsys, "--fault", "lost-response", "--approve")
    assert pending["run"]["state"] == "NEEDS_RECONCILIATION"
    assert "action.unknown" in _types(pending)
    resolved = _run(capsys, "--fault", "lost-response", "--approve", "--reconcile")
    assert resolved["run"]["state"] == "SUCCEEDED"
    assert resolved["fixture_erp_create_calls"] == 1, "no write was re-sent"


def test_plugins_listing_is_metadata_only(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["plugins"]) == 0
    out = capsys.readouterr().out
    assert "domain-erp 0.1.0 [domain]" in out and "enabled" in out
