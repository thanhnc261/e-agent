"""ERP-04..08 through the real kernel, SHACL engine and fixture ERP (I10/I11)."""

import json
from typing import Any

import pytest
from e_agent.server.cli import main


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> dict[str, Any]:
    assert main(["demo", "--json", *args]) == 0
    return json.loads(capsys.readouterr().out)  # type: ignore[no-any-return]


def _payloads(result: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [e["payload"] for e in result["events"] if e["type"] == kind]


def _failed_rules(validation: dict[str, Any]) -> set[str]:
    return {f["rule_id"] for f in validation["findings"] if f["status"] == "FAIL"}


@pytest.mark.parametrize(
    ("task", "broken_rule"),
    [("amend-rfq", "AM-002"), ("quotation", "SQ-003"), ("crm-lead", "CL-002")],
)
def test_writes_are_blocked_by_the_named_rule_then_repaired_and_verified(
    capsys: pytest.CaptureFixture[str], task: str, broken_rule: str
) -> None:
    result = _run(capsys, "--task", task, "--driver-mode", "invalid-then-repair", "--approve")
    first, second = _payloads(result, "validation.completed")[:2]
    assert _failed_rules(first) == {broken_rule}
    assert second["status"] == "PASS"
    outcome = _payloads(result, "outcome.reported")[-1]
    assert outcome["status"] == "VERIFIED"
    assert result["run"]["state"] == "SUCCEEDED"
    assert result["fixture_erp_create_calls"] == 1


@pytest.mark.parametrize(
    ("task", "scenario", "rule"),
    [("amend-rfq", "rfq-confirmed", "AM-001"), ("quotation", "unsaleable-product", "SQ-002")],
)
def test_invalid_targets_are_blocked_and_nothing_is_written(
    capsys: pytest.CaptureFixture[str], task: str, scenario: str, rule: str
) -> None:
    result = _run(capsys, "--task", task, "--scenario", scenario, "--approve")
    assert result["run"]["state"] == "FAILED"
    assert rule in _failed_rules(_payloads(result, "validation.completed")[0])
    assert result["fixture_erp_create_calls"] == 0
    assert "approval.requested" not in [e["type"] for e in result["events"]]


@pytest.mark.parametrize("task", ["late-orders", "overdue-invoices"])
def test_read_only_answers_fail_verification_when_wrong_then_pass(
    capsys: pytest.CaptureFixture[str], task: str
) -> None:
    result = _run(capsys, "--task", task, "--driver-mode", "wrong-answer-then-correct")
    statuses = [p["status"] for p in _payloads(result, "outcome.reported")]
    assert statuses == ["FAILED", "VERIFIED"]
    assert result["run"]["state"] == "SUCCEEDED"
    assert result["fixture_erp_create_calls"] == 0  # read-only: never a write
    assert "approval.requested" not in [e["type"] for e in result["events"]]


def test_late_orders_and_overdue_invoices_match_the_fixture(
    capsys: pytest.CaptureFixture[str],
) -> None:
    late = _run(capsys, "--task", "late-orders")
    args = _payloads(late, "proposal.created")[0]
    assert args["arguments"]["late_order_refs"] == ["order:so-1", "order:so-4"]
    overdue = _run(capsys, "--task", "overdue-invoices")
    args = _payloads(overdue, "proposal.created")[0]["arguments"]
    assert args["overdue_invoice_refs"] == ["invoice:inv-1", "invoice:inv-4", "invoice:inv-5"]
    assert args["totals"] == [
        {"currency": "USD", "total": "120.5"},
        {"currency": "VND", "total": "750"},
    ]


@pytest.mark.parametrize("task", ["amend-rfq", "quotation", "crm-lead"])
def test_lost_response_reconciles_without_a_second_write(
    capsys: pytest.CaptureFixture[str], task: str
) -> None:
    result = _run(capsys, "--task", task, "--fault", "lost-response", "--approve", "--reconcile")
    assert result["run"]["state"] == "SUCCEEDED"
    assert result["fixture_erp_create_calls"] == 1
