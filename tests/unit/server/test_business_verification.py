"""Independent read-back must reject changes beyond the approved business operation."""

from dataclasses import replace

import pytest
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.run import RunState
from e_agent.plugins.erp.domain.crm import LEAD_READ
from e_agent.plugins.erp.domain.procurement import PURCHASE_ORDER_READ
from e_agent.plugins.erp.domain.sales import QUOTATION_READ
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import load_profile


@pytest.mark.parametrize(
    ("task", "field", "value"),
    [
        ("draft-po", "supplier_ref", "supplier:other"),
        ("draft-po", "product_ref", "product:other"),
        ("draft-po", "unit", "other-unit"),
        ("draft-po", "currency", "other-currency"),
        ("draft-po", "quantity", "999"),
        ("draft-po", "unit_price", "999"),
        ("draft-po", "subtotal", "999"),
        ("draft-po", "requested_date", "2099-01-01"),
        ("draft-po", "line_count", 2),
        ("draft-po", "state", "purchase"),
        ("draft-po", "operation_key", "wrong-operation"),
        ("draft-po", "external_ref", "wrong-reference"),
        ("amend-rfq", "quantity", "999"),
        ("amend-rfq", "requested_date", "2099-01-01"),
        ("amend-rfq", "state", "purchase"),
        ("amend-rfq", "subtotal", "999"),
        ("amend-rfq", "operation_key", "wrong-operation"),
        ("amend-rfq", "external_ref", "wrong-reference"),
        ("quotation", "customer_ref", "customer:other"),
        ("quotation", "product_ref", "product:other"),
        ("quotation", "unit", "other-unit"),
        ("quotation", "currency", "other-currency"),
        ("quotation", "quantity", "999"),
        ("quotation", "unit_price", "999"),
        ("quotation", "subtotal", "999"),
        ("quotation", "state", "sale"),
        ("quotation", "operation_key", "wrong-operation"),
        ("quotation", "external_ref", "wrong-reference"),
        ("crm-lead", "name", "Wrong lead"),
        ("crm-lead", "contact_ref", "contact:other"),
        ("crm-lead", "team_ref", "team:other"),
        ("crm-lead", "owner_ref", "owner:other"),
        ("crm-lead", "source_ref", "source:other"),
        ("crm-lead", "expected_revenue", "999"),
        ("crm-lead", "operation_key", "wrong-operation"),
        ("crm-lead", "external_ref", "wrong-reference"),
        ("amend-rfq", "supplier_ref", "supplier:other"),
        ("amend-rfq", "product_ref", "product:other"),
        ("amend-rfq", "unit", "other-unit"),
        ("amend-rfq", "currency", "other-currency"),
        ("amend-rfq", "unit_price", "200"),
        ("amend-rfq", "line_count", 2),
        ("quotation", "line_count", 2),
        ("quotation", "line_count", None),
    ],
)
async def test_committed_effect_with_inexact_readback_is_not_verified(task, field, value):
    runtime = await build_runtime(load_profile(fixture_profile_path()), task_kind=task)
    [erp] = runtime.registry.plugin_executors["fixture-erp"]
    original = erp.read

    async def corrupt(ctx, binding, request):
        observation = await original(ctx, binding, request)
        if request.contract_id in {PURCHASE_ORDER_READ, QUOTATION_READ, LEAD_READ}:
            collection = {
                PURCHASE_ORDER_READ: "orders",
                QUOTATION_READ: "quotations",
                LEAD_READ: "leads",
            }[request.contract_id]
            observation = replace(
                observation,
                data={collection: [{**row, field: value} for row in observation.data[collection]]},
            )
        return observation

    erp.read = corrupt
    run = await runtime.coordinator.start_run(runtime.operator, task, runtime.scope)
    presentation = await runtime.coordinator.pending_approval(
        runtime.operator.tenant_id, run.run_id
    )
    run = await runtime.coordinator.decide(
        actor=runtime.operator,
        run_id=run.run_id,
        action_id=presentation.action_id,
        action_digest=presentation.digest,
        expected_run_revision=presentation.run_revision,
        decision=ApprovalDecision.APPROVED,
    )
    assert run.state is RunState.FAILED
    actions = await runtime.store.list_actions(runtime.operator.tenant_id, run.run_id)
    receipts = await runtime.store.list_receipts(runtime.operator.tenant_id, actions[-1].action_id)
    assert str(receipts[-1].status) == "COMMITTED"
    events = await runtime.store.list_events(runtime.operator.tenant_id, run.run_id)
    assert not any(
        e.type == "outcome.reported" and e.payload["status"] == "VERIFIED" for e in events
    )


@pytest.mark.parametrize("acknowledgement", ["repeat-proposal", "budget-exhausted"])
async def test_verified_answer_finishes_after_one_bounded_acknowledgement(acknowledgement):
    from e_agent.plugins.erp.domain.testing.scripted_tasks import ScriptedErpDriver
    from e_agent.sdk.errors import DriverBudgetExceeded
    from e_agent.sdk.ports import ProposeAction

    class Driver:
        driver_id = "fixture-answer-acknowledgement"

        def __init__(self):
            self.delegate = ScriptedErpDriver(
                connection_id="conn-fixture-erp", task_kind="shortage"
            )
            self.proposal = None
            self.acknowledgements = 0

        async def advance(self, ctx, step_input):
            if step_input.action_result is not None:
                self.acknowledgements += 1
                if acknowledgement == "budget-exhausted":
                    raise DriverBudgetExceeded("final response cap")
                return self.proposal
            step = await self.delegate.advance(ctx, step_input)
            if isinstance(step, ProposeAction):
                self.proposal = step
            return step

    driver = Driver()
    runtime = await build_runtime(
        load_profile(fixture_profile_path()), driver_factory=lambda registry: driver
    )
    run = await runtime.coordinator.start_run(runtime.operator, "shortage", runtime.scope)
    assert run.state is (
        RunState.FAILED if acknowledgement == "budget-exhausted" else RunState.SUCCEEDED
    )
    assert driver.acknowledgements == 1
    actions = await runtime.store.list_actions(runtime.operator.tenant_id, run.run_id)
    assert len(actions) == 1 and str(actions[0].state) == "VERIFIED"
    assert runtime.diagnostics()["fixture-erp"]["create_calls"] == 0
    events = await runtime.store.list_events(runtime.operator.tenant_id, run.run_id)
    if acknowledgement == "repeat-proposal":
        assert any(event.type == "message.final" for event in events)
    if acknowledgement == "budget-exhausted":
        assert any(event.type == "budget.exhausted" for event in events)


async def test_verified_recommendation_can_precede_an_approved_purchase_order():
    from e_agent.plugins.erp.domain.testing.scripted_tasks import ScriptedErpDriver
    from e_agent.sdk.ports import FinalAnswer

    class Driver:
        driver_id = "fixture-recommend-then-purchase"

        def __init__(self):
            self.recommend = ScriptedErpDriver(
                connection_id="conn-fixture-erp", task_kind="recommend"
            )
            self.purchase = ScriptedErpDriver(
                connection_id="conn-fixture-erp", task_kind="draft-po"
            )
            self.recommended = False

        async def advance(self, ctx, step_input):
            if step_input.action_result is not None:
                if self.recommended:
                    return FinalAnswer(text="Approved purchase order independently verified.")
                self.recommended = True
                return await self.purchase.advance(ctx, replace(step_input, action_result=None))
            return await self.recommend.advance(ctx, step_input)

    runtime = await build_runtime(
        load_profile(fixture_profile_path()), driver_factory=lambda registry: Driver()
    )
    run = await runtime.coordinator.start_run(
        runtime.operator, "create purchase order", runtime.scope
    )
    assert run.state is RunState.WAITING_APPROVAL
    presentation = await runtime.coordinator.pending_approval(
        runtime.operator.tenant_id, run.run_id
    )
    run = await runtime.coordinator.decide(
        actor=runtime.operator,
        run_id=run.run_id,
        action_id=presentation.action_id,
        action_digest=presentation.digest,
        expected_run_revision=presentation.run_revision,
        decision=ApprovalDecision.APPROVED,
    )
    assert (
        run.state is RunState.SUCCEEDED
        and runtime.diagnostics()["fixture-erp"]["create_calls"] == 1
    )
