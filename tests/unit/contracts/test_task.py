from datetime import timedelta

import pytest
from e_agent.contracts.context import Budgets
from e_agent.contracts.task import AcceptanceSpec, RequiredEffect, TaskDefinition
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
