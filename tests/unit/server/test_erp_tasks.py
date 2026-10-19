"""ERP-04..08 through the real kernel, SHACL engine and fixture ERP (I10/I11)."""

import json
from typing import Any

import pytest
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.cli import main

FIXTURE = ("--profile", str(fixture_profile_path()))


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> dict[str, Any]:
    assert main([*FIXTURE, "demo", "--json", *args]) == 0
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
    assert result["provider_diagnostics"]["fixture-erp"]["create_calls"] == 1


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
    assert result["provider_diagnostics"]["fixture-erp"]["create_calls"] == 0
    assert "approval.requested" not in [e["type"] for e in result["events"]]


@pytest.mark.parametrize("task", ["late-orders", "overdue-invoices"])
def test_read_only_answers_fail_verification_when_wrong_then_pass(
    capsys: pytest.CaptureFixture[str], task: str
) -> None:
    result = _run(capsys, "--task", task, "--driver-mode", "wrong-answer-then-correct")
    statuses = [p["status"] for p in _payloads(result, "outcome.reported")]
    assert statuses == ["FAILED", "VERIFIED"]
    assert result["run"]["state"] == "SUCCEEDED"
    assert (
        result["provider_diagnostics"]["fixture-erp"]["create_calls"] == 0
    )  # read-only: never a write
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
    assert result["provider_diagnostics"]["fixture-erp"]["create_calls"] == 1


# -- execution IR shadow through the CLI (Task 2c.5, D8) -------------------------------------
@pytest.fixture
def shadow_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fixture profile with ``execution_ir: shadow``; the CLI passes the preset kind."""
    from e_agent.contracts.features import FeatureMode, Features
    from e_agent.server import cli

    real = cli.load_profile

    def load(path: Any) -> Any:
        profile = real(path)
        return profile.model_copy(update={"features": Features(execution_ir=FeatureMode.SHADOW)})

    monkeypatch.setattr(cli, "load_profile", load)


@pytest.mark.parametrize("task", ["draft-po", "amend-rfq", "quotation", "crm-lead"])
def test_shadow_compiles_each_erp_write_with_the_action_digest(
    capsys: pytest.CaptureFixture[str], shadow_profile: None, task: str
) -> None:
    result = _run(capsys, "--task", task, "--approve")
    (compiled,) = _payloads(result, "ir.plan_compiled")
    (requested,) = _payloads(result, "approval.requested")
    assert compiled["digest_matches"] is True
    assert compiled["plan_digest"] == requested["digest"]
    assert (compiled["task_id"], compiled["step_count"]) == (task, 1)
    assert not _payloads(result, "ir.shadow_failed")
    assert result["run"]["state"] == "SUCCEEDED"
    assert result["run"]["task_id"] == task
    assert result["provider_diagnostics"]["fixture-erp"]["create_calls"] == 1


def test_shadow_compiles_only_the_repaired_proposal(
    capsys: pytest.CaptureFixture[str], shadow_profile: None
) -> None:
    result = _run(
        capsys, "--task", "quotation", "--driver-mode", "invalid-then-repair", "--approve"
    )
    assert [p["status"] for p in _payloads(result, "validation.completed")][:2] == ["FAIL", "PASS"]
    (compiled,) = _payloads(result, "ir.plan_compiled")
    assert compiled["digest_matches"] is True
    assert result["run"]["state"] == "SUCCEEDED"


def test_shadow_leaves_read_only_answers_alone(
    capsys: pytest.CaptureFixture[str], shadow_profile: None
) -> None:
    """Answers are not write proposals: no approval digest, so no shadow step."""
    result = _run(capsys, "--task", "late-orders")
    types = [e["type"] for e in result["events"]]
    assert not [t for t in types if t.startswith("ir.")]
    assert result["run"]["state"] == "SUCCEEDED"


async def test_shadow_unresolved_answer_run_records_task_unresolved() -> None:
    """An API-style run (free text through `admit_run`, no task kind, D8) that ends in a
    structured answer records exactly one `ir.shadow_failed` (`IR_TASK_UNRESOLVED`), at
    creation, and nothing else; its state, revision and outcome equal `off`."""
    from e_agent.contracts.features import FeatureMode, Features
    from e_agent.contracts.run import ReasonCode
    from e_agent.kernel.features import FALLBACK_MESSAGES
    from e_agent.server.bootstrap import build_runtime
    from e_agent.server.profile import load_profile

    base = load_profile(fixture_profile_path())
    seen = {}
    for mode in (FeatureMode.OFF, FeatureMode.SHADOW):
        profile = base.model_copy(update={"features": Features(execution_ir=mode)})
        rt = await build_runtime(profile, task_kind="late-orders")
        tenant = rt.operator.tenant_id
        run_id, _ = await rt.coordinator.admit_run(
            rt.operator,
            "Which sales orders are late?",
            rt.scope,
            run_id="run-api-answer",
            idempotency_key="api-answer",
            request_digest="d",
        )
        run = await rt.coordinator.start_admitted_run(tenant, run_id)
        events = await rt.store.list_events(tenant, run_id)
        seen[mode] = {
            "end": (run.state, run.reason_code, run.revision),
            "outcomes": [e.payload["status"] for e in events if e.type == "outcome.reported"],
            "types": [str(e.type) for e in events if not str(e.type).startswith("ir.")],
            "ir": [
                (str(e.type), e.payload, e.action_id) for e in events if e.type.startswith("ir.")
            ],
            "steps": await rt.store.list_steps(tenant, run_id),
        }
    off, shadow = seen[FeatureMode.OFF], seen[FeatureMode.SHADOW]
    assert shadow["ir"] == [
        (
            "ir.shadow_failed",
            {
                "reason_code": "ir_task_unresolved",
                "message": FALLBACK_MESSAGES[ReasonCode.IR_TASK_UNRESOLVED],
            },
            None,
        )
    ]
    assert off["ir"] == [] and shadow["steps"] == []
    assert off["outcomes"] == ["VERIFIED"]
    for key in ("end", "outcomes", "types"):
        assert shadow[key] == off[key], key
