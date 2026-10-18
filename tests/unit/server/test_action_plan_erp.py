"""A two-step ERP plan on the simulator (Task 2c.7, ADR 0025).

The scripted driver's ``two-step-plan`` mode proposes two draft POs; the second copies
``requested_date`` through lineage from the first PO as its verifier read it back. Two orders
for one demand is a fixture demonstration of lineage, not a procurement scenario. Only a
fixture profile may raise ``max_admitted_writes`` to 2.
"""

from typing import Any

from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.plugins.erp.domain.testing.scripted_tasks import (
    FIRST_PO,
    SECOND_PO,
    TWO_STEP_PLAN,
    ScriptedErpDriver,
)
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.bootstrap import build_runtime
from e_agent.server.cli import demo_prompt, plan_lines
from e_agent.server.profile import Profile, load_profile

CONN = "conn-fixture-erp"
DRAFT_PO = "draft-po"
CREATE_PO = "procurement.purchase-order.create-draft.v1"


def _profile() -> Profile:
    profile = load_profile(fixture_profile_path())
    return profile.model_copy(
        update={
            "features": Features(execution_ir=FeatureMode.ON),
            "budgets": profile.budgets.model_copy(update={"max_admitted_writes": 2}),
        }
    )


def _plan_driver(registry: Any) -> ScriptedErpDriver:
    return ScriptedErpDriver(connection_id=CONN, mode=TWO_STEP_PLAN)


async def test_erp_two_step_fixture_scenario() -> None:
    rt = await build_runtime(_profile(), driver_factory=_plan_driver)
    tenant = rt.operator.tenant_id
    preset = rt.registry.task_presets[DRAFT_PO]
    prompt = demo_prompt(preset, rt.profile.driver)
    run = await rt.coordinator.start_run(rt.operator, prompt, rt.scope, task_kind=DRAFT_PO)
    assert run.state is RunState.WAITING_APPROVAL

    pres = await rt.coordinator.pending_approval(tenant, run.run_id)
    assert [s.step_id for s in pres.plan_steps] == [FIRST_PO, SECOND_PO]
    assert pres.plan_steps[1].depends_on == (FIRST_PO,)
    shown = "\n".join(plan_lines(pres))
    assert "from step 1: /requested_date" in shown

    run = await rt.coordinator.decide(
        actor=rt.operator,
        run_id=run.run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)

    actions = await rt.store.list_actions(tenant, run.run_id)
    assert [(a.contract_id, str(a.state)) for a in actions] == [
        (CREATE_PO, "VERIFIED"),
        (CREATE_PO, "VERIFIED"),
    ]
    (approval,) = await rt.store.list_approvals(tenant, actions[0].action_id)
    assert approval.action_digest == pres.digest
    assert await rt.store.list_approvals(tenant, actions[1].action_id) == []
    assert rt.diagnostics()["fixture-erp"]["create_calls"] == 2

    events = await rt.store.list_events(tenant, run.run_id)
    (lineage,) = [e.payload for e in events if e.type is RunEventType.IR_LINEAGE_RESOLVED]
    (resolved,) = lineage["values"]
    assert (resolved["argument"], resolved["from_step"], resolved["path"]) == (
        "/requested_date",
        FIRST_PO,
        "/requested_date",
    )
    assert actions[1].arguments["requested_date"] == resolved["value"]
    assert actions[0].arguments["requested_date"] == resolved["value"]
    assert [(a.plan_id is not None, a.step_index) for a in actions] == [(True, 0), (True, 1)]
    verified = [e.payload["step_id"] for e in events if e.type is RunEventType.IR_STEP_VERIFIED]
    assert verified == [FIRST_PO, SECOND_PO]
