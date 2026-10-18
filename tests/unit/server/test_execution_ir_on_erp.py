"""`execution_ir: on` with the ERP domain pack on the simulator (Task 2c.6, ADR 0028).

The kernel suite imports no plugin, so the draft-po acceptance cases live here: a verified
draft PO meets the definition's effects alternative, a verified zero-shortage answer meets
its answer alternative (target §1.3, the `answer_condition`), and an accurate answer that
reports a positive shortage, with no PO, leaves acceptance unmet (Codex review C-2). Startup
in `on` refuses a definition whose capability the driver could not be offered (2c.2 R-1).
"""

from typing import Any

import pytest
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.contracts.step import StepKind, StepStatus
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.plugins.erp.domain.testing.scripted_driver import ScriptedProcurementDriver
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.bootstrap import Runtime, build_runtime
from e_agent.server.cli import demo_prompt
from e_agent.server.profile import Profile, load_profile

CONN = "conn-fixture-erp"
DRAFT_PO = "draft-po"
CREATE_PO = "procurement.purchase-order.create-draft.v1"
SHORTAGE = "procurement.shortage.answer.v1"


def _profile(mode: FeatureMode = FeatureMode.ON) -> Profile:
    profile = load_profile(fixture_profile_path())
    return profile.model_copy(update={"features": Features(execution_ir=mode)})


async def _start(rt: Runtime) -> Any:
    preset = rt.registry.task_presets[DRAFT_PO]
    prompt = demo_prompt(preset, rt.profile.driver)
    return await rt.coordinator.start_run(rt.operator, prompt, rt.scope, task_kind=DRAFT_PO)


async def _actions(rt: Runtime, run_id: str) -> list[tuple[str, str]]:
    actions = await rt.store.list_actions(rt.operator.tenant_id, run_id)
    return [(a.contract_id, str(a.state)) for a in actions]


async def test_on_draft_po_run_verifies_through_host_only_reads_and_records_steps() -> None:
    """The verifier reads a host-only capability outside the tool set: the kernel's own reads
    are not narrowed, so the PO verifies, every stage has its step rows, and acceptance holds."""
    rt = await build_runtime(_profile())
    run = await _start(rt)
    pres = await rt.coordinator.pending_approval(rt.operator.tenant_id, run.run_id)
    run = await rt.coordinator.decide(
        actor=rt.operator,
        run_id=run.run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert await _actions(rt, run.run_id) == [(CREATE_PO, "VERIFIED")]
    steps = await rt.store.list_steps(rt.operator.tenant_id, run.run_id)
    assert [(s.kind, s.status) for s in steps if s.status is not StepStatus.STARTED] == [
        (StepKind.VALIDATE, StepStatus.SUCCEEDED),
        (StepKind.APPROVAL_WAIT, StepStatus.SUCCEEDED),
        (StepKind.DISPATCH, StepStatus.SUCCEEDED),
        (StepKind.VERIFY, StepStatus.SUCCEEDED),
    ]


async def test_on_acceptance_met_by_verified_no_op_answer() -> None:
    """Zero shortage: the scripted driver answers instead of writing; the verifier computes a
    shortage of "0", which meets draft-po's answer alternative without a PO."""
    rt = await build_runtime(
        _profile(), plugin_settings={"fixture-erp": {"scenario": "zero-shortage"}}
    )
    run = await _start(rt)
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.ANSWERED)
    assert await _actions(rt, run.run_id) == [(SHORTAGE, "VERIFIED")]
    assert rt.diagnostics()["fixture-erp"]["create_calls"] == 0
    events = await rt.store.list_events(rt.operator.tenant_id, run.run_id)
    (outcome,) = [e.payload for e in events if e.type is RunEventType.OUTCOME_REPORTED]
    shortage = [c for c in outcome["checks"] if c["name"] == "shortage"]
    assert [(c["passed"], c["expected"]) for c in shortage] == [(True, "0")]


def _shortage_driver(registry: Any) -> ScriptedProcurementDriver:
    """A driver that answers the shortage question on a draft-po run instead of writing."""
    return ScriptedProcurementDriver(connection_id=CONN, task_kind="shortage")


@pytest.mark.parametrize(
    ("mode", "state", "code"),
    [
        (FeatureMode.OFF, RunState.SUCCEEDED, ReasonCode.ANSWERED),
        (FeatureMode.ON, RunState.FAILED, ReasonCode.ACCEPTANCE_UNMET),
    ],
)
async def test_on_acceptance_unmet_for_positive_shortage_answer(
    mode: FeatureMode, state: RunState, code: ReasonCode
) -> None:
    """An accurate, verified answer reporting a positive shortage, and no PO, does not meet
    draft-po's acceptance in `on` (Codex C-2); `off` keeps today's outcome for the same run."""
    rt = await build_runtime(_profile(mode), driver_factory=_shortage_driver)
    run = await _start(rt)
    assert (run.state, run.reason_code) == (state, code)
    assert await _actions(rt, run.run_id) == [(SHORTAGE, "VERIFIED")]
    events = await rt.store.list_events(rt.operator.tenant_id, run.run_id)
    (outcome,) = [e.payload for e in events if e.type is RunEventType.OUTCOME_REPORTED]
    assert outcome["status"] == "VERIFIED"
    shortage = [c for c in outcome["checks"] if c["name"] == "shortage"]
    assert len(shortage) == 1 and shortage[0]["passed"] and shortage[0]["expected"] != "0"


def _two_connections(profile: Profile) -> Profile:
    """A second connection with the offers read bound on both."""
    second = profile.connections[0].model_copy(update={"connection_id": "conn-fixture-erp-2"})
    bindings = dict(profile.bindings)
    bindings["fixture-erp.procurement.offers"] = (CONN, "conn-fixture-erp-2")
    return profile.model_copy(
        update={"connections": [*profile.connections, second], "bindings": bindings}
    )


async def test_on_refuses_startup_for_capability_bound_on_two_connections() -> None:
    """2c.2 R-1 (PR-10): in `on`, a definition naming a capability the driver cannot be
    offered (its bindings sit on two connections, so `tool_specs` leaves it out) refuses
    startup with a stated reason instead of dropping it from the run's tool set."""
    with pytest.raises(KernelError) as caught:
        await build_runtime(_two_connections(_profile()))
    assert caught.value.code is ErrorCode.STARTUP_REJECTED
    message = str(caught.value)
    assert "execution_ir: on" in message and "procurement.offers.read.v1" in message
    assert "more than one connection" in message


@pytest.mark.parametrize("mode", [FeatureMode.OFF, FeatureMode.SHADOW])
async def test_off_and_shadow_startup_keep_two_connection_bindings(mode: FeatureMode) -> None:
    rt = await build_runtime(_two_connections(_profile(mode)))
    assert rt.coordinator is not None
