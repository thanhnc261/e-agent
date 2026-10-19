from datetime import UTC, datetime, timedelta

import pytest
from e_agent.contracts.context import Budgets
from e_agent.contracts.outcome import OutcomeCheck, OutcomeReport, OutcomeStatus
from e_agent.contracts.task import (
    AcceptanceSpec,
    AnswerCondition,
    RequiredEffect,
    TaskDefinition,
    answer_condition_met,
)
from pydantic import ValidationError


def _definition(**overrides: object) -> TaskDefinition:
    fields: dict[str, object] = {
        "task_id": "purchase_order",
        "version": "1",
        "title": "Draft a purchase order",
        "goal_template": "Draft a PO for {item}",
        "capabilities": ("erp.product.read.v1", "erp.purchase.create.v1"),
        "acceptance": AcceptanceSpec(
            required_effects=(RequiredEffect(contract_id="erp.purchase.create.v1"),)
        ),
    }
    fields.update(overrides)
    return TaskDefinition.model_validate(fields)


def test_task_definition_requires_capabilities_and_acceptance() -> None:
    task = _definition()
    assert task.capabilities == ("erp.product.read.v1", "erp.purchase.create.v1")
    assert task.acceptance.required_effects[0].min_verified == 1
    assert task.budgets is None
    assert task.approval_ttl is None
    with pytest.raises(ValidationError, match="at least one capability"):
        _definition(capabilities=())
    without_acceptance = _definition().model_dump()
    del without_acceptance["acceptance"]
    with pytest.raises(ValidationError, match="acceptance"):
        TaskDefinition.model_validate(without_acceptance)


def test_task_definition_refuses_duplicate_capabilities() -> None:
    with pytest.raises(ValidationError, match="duplicate capability"):
        _definition(capabilities=("erp.product.read.v1", "erp.product.read.v1"))


def test_acceptance_names_only_capabilities_of_the_definition() -> None:
    with pytest.raises(ValidationError, match="not among the definition's capabilities"):
        _definition(
            acceptance=AcceptanceSpec(
                required_effects=(RequiredEffect(contract_id="erp.invoice.create.v1"),)
            )
        )
    with pytest.raises(ValidationError, match="not among the definition's capabilities"):
        _definition(acceptance=AcceptanceSpec(required_answer="erp.answer.stock.v1"))


def test_required_effect_counts_at_least_one() -> None:
    with pytest.raises(ValidationError):
        RequiredEffect(contract_id="erp.purchase.create.v1", min_verified=0)


def test_task_definition_budgets_and_ttl_are_optional_overrides() -> None:
    task = _definition(budgets=Budgets(max_admitted_writes=1), approval_ttl=timedelta(minutes=5))
    assert task.budgets is not None
    assert task.budgets.model_fields_set == {"max_admitted_writes"}
    assert task.approval_ttl == timedelta(minutes=5)
    with pytest.raises(ValidationError, match="approval_ttl must be positive"):
        _definition(approval_ttl=timedelta(0))


ANSWER = "erp.answer.stock.v1"
ZERO = AnswerCondition(check="shortage", expected="0")


def test_answer_condition_requires_required_answer() -> None:
    with pytest.raises(ValidationError, match="answer_condition needs a required_answer"):
        AcceptanceSpec(answer_condition=ZERO)
    with pytest.raises(ValidationError, match="answer_condition needs a required_answer"):
        AcceptanceSpec.model_validate(
            {
                "required_effects": [{"contract_id": "erp.purchase.create.v1"}],
                "answer_condition": {"check": "shortage", "expected": "0"},
            }
        )
    spec = AcceptanceSpec(required_answer=ANSWER, answer_condition=ZERO)
    assert spec.answer_condition == ZERO
    assert AcceptanceSpec().answer_condition is None
    with pytest.raises(ValidationError):
        AnswerCondition(check="shortage")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        AnswerCondition(check="shortage", expected="0", observed="0")  # type: ignore[call-arg]


def _report(status: OutcomeStatus, *checks: OutcomeCheck) -> OutcomeReport:
    return OutcomeReport(
        run_id="run_1",
        action_id="act_1",
        status=status,
        checks=checks,
        verifier_id="v",
        verifier_version="1",
        reported_at=datetime(2026, 10, 18, tzinfo=UTC),
    )


def _check(
    expected: str, observed: str, passed: bool = True, name: str = "shortage"
) -> OutcomeCheck:
    return OutcomeCheck(name=name, passed=passed, expected=expected, observed=observed)


def test_answer_condition_reads_the_verifier_check_not_model_arguments() -> None:
    """The condition compares the verifier's own ``expected``; the model's claim (the
    check's ``observed``, the action's arguments) never counts (Codex review C-2)."""
    spec = AcceptanceSpec(required_answer=ANSWER, answer_condition=ZERO)
    verified = OutcomeStatus.VERIFIED
    # The verifier computed 0: met, whatever the model observed.
    assert answer_condition_met(spec, _report(verified, _check("0", "0")))
    assert answer_condition_met(spec, _report(verified, _check("0", "7")))
    # The verifier computed a positive shortage: not met, even when the model claimed 0.
    assert not answer_condition_met(spec, _report(verified, _check("7", "0")))
    assert not answer_condition_met(spec, _report(verified, _check("7", "7")))
    # Exact string equality: no numeric coercion.
    assert not answer_condition_met(spec, _report(verified, _check("0.0", "0")))
    # A failing check, a failed report, or no check of that name: not met.
    assert not answer_condition_met(spec, _report(verified, _check("0", "0", passed=False)))
    assert not answer_condition_met(spec, _report(OutcomeStatus.FAILED, _check("0", "0")))
    assert not answer_condition_met(spec, _report(OutcomeStatus.UNKNOWN, _check("0", "0")))
    assert not answer_condition_met(spec, _report(verified, _check("0", "0", name="available")))
    assert not answer_condition_met(spec, _report(verified))
    # Every check of that name must agree.
    assert not answer_condition_met(spec, _report(verified, _check("0", "0"), _check("7", "7")))
    # Without a condition the verified answer alone meets the alternative; without a
    # required answer there is no answer alternative.
    plain = AcceptanceSpec(required_answer=ANSWER)
    assert answer_condition_met(plain, _report(verified, _check("7", "7")))
    assert not answer_condition_met(plain, _report(OutcomeStatus.FAILED, _check("7", "7")))
    assert not answer_condition_met(AcceptanceSpec(), _report(verified, _check("0", "0")))
