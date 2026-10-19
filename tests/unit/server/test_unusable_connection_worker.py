"""The worker path of a read or answer on an unusable connection (Task 2c.8c, review P-1).

Before 2c.8c the FORBIDDEN raised out of the driver turn reached the worker's ``_mark_failed``,
which applied the crash rules and ended the run FAILED ``INTERRUPTED``: the wrong reason for a
run that was refused, not interrupted. Now the run ends on its own terminal reason inside
the start claim, and nothing is left queued.
"""

from dataclasses import dataclass
from typing import Any

import pytest
from e_agent.contracts.context import TaskContext
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.kernel.gateway import UNUSABLE_CONNECTION
from e_agent.plugins.erp.domain.testing.scripted_tasks import ScriptedErpDriver
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.sdk.ports import DriverInput, DriverStep, ProposeAction
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import load_profile

CONN, NOWHERE = "conn-fixture-erp", "conn-nowhere"
LATE_ORDERS = "late-orders"
"""A read-only answer task of the fixture ERP: it reads open orders, then answers."""


@dataclass
class AnswerElsewhere:
    """The scripted late-orders driver, with its answer moved to ``NOWHERE``."""

    inner: ScriptedErpDriver
    driver_id: str = "answer-elsewhere"

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        step = await self.inner.advance(ctx, step_input)
        if isinstance(step, ProposeAction):
            proposal = step.proposal.model_copy(update={"connection_id": NOWHERE})
            return ProposeAction(proposal=proposal)
        return step


def _driver(case: str) -> Any:
    if case == "read":  # reads on a connection outside the run's scope, again and again
        return lambda _registry: ScriptedErpDriver(connection_id=NOWHERE, task_kind=LATE_ORDERS)
    return lambda _registry: AnswerElsewhere(
        ScriptedErpDriver(connection_id=CONN, task_kind=LATE_ORDERS)
    )


@pytest.mark.parametrize("mode", ["off", "on"])
@pytest.mark.parametrize(
    ("case", "reason"),
    [("read", ReasonCode.BUDGET_EXHAUSTED), ("answer", ReasonCode.VALIDATION_FAILED)],
)
async def test_worker_ends_a_refused_run_on_its_own_reason(
    mode: str, case: str, reason: ReasonCode
) -> None:
    from e_agent.server.api import ApiState

    profile = load_profile(fixture_profile_path())
    if mode == "on":
        profile = profile.model_copy(update={"features": Features(execution_ir=FeatureMode.ON)})
    rt = await build_runtime(profile, driver_factory=_driver(case))
    state = ApiState(rt)
    tenant = rt.operator.tenant_id
    run_id, _ = await rt.coordinator.admit_run(
        rt.operator,
        "list the late orders",
        rt.scope,
        run_id=f"run-{case}-{mode}",
        idempotency_key=f"key-{case}-{mode}",
        request_digest=f"digest-{case}-{mode}",
        task_kind=LATE_ORDERS if mode == "on" else None,
    )
    claim = await rt.store.claim_work("worker-test")
    assert claim is not None and claim.kind == "start"
    await state._run_work(claim)

    run = await rt.store.get_run(tenant, run_id)
    assert (run.state, run.reason_code) == (RunState.FAILED, reason), run.reason
    assert not await rt.store.has_pending_work(tenant, run_id)
    assert await rt.store.claim_work("worker-test") is None
    events = await rt.store.list_events(tenant, run_id)
    if case == "read":
        rejected = [e for e in events if e.type is RunEventType.READ_REJECTED]
        assert rejected and {e.payload["code"] for e in rejected} == {UNUSABLE_CONNECTION}
    else:
        rules = {
            f["rule_id"]
            for e in events
            if e.type is RunEventType.VALIDATION_COMPLETED
            for f in e.payload.get("findings", [])
        }
        assert "KERNEL-CONNECTION" in rules
    assert rt.diagnostics()["fixture-erp"]["create_calls"] == 0
