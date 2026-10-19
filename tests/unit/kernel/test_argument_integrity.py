"""Argument integrity before reservation (Task 2c.8b, Codex C-3, PR-08, PR-16).

A plugin validator gets a copy of the arguments, never kernel-owned state; and the last
check before a reservation compares the action as it will be dispatched with what the
approval bound (the approval digest for a single action, the approved step input with its
lineage substituted for a plan step). The single-action path is shared with ``off``.
Both stores run through `run_store` (ENG-STORE-1).
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.plan import ActionPlan
from e_agent.contracts.run import ReasonCode, RunState

from .conftest import (
    TENANT,
    Kernel,
    MetadataDriver,
    NotesPlanDriver,
    two_step_plan,
)
from .test_action_plan_failures import (
    _actions,
    _decide,
    _of,
    _plan_kernel,
    _rules,
    _start,
    _step_statuses,
)

MakeKernel = Callable[..., Kernel]
ON = Features(execution_ir=FeatureMode.ON)
APPROVED, MUTATED = "approved", "mutated"


# -- C-3: argument integrity before reservation --------------------------------------------
def _metadata_plan() -> ActionPlan:
    plan = two_step_plan()
    second = plan.steps[1]
    arguments = {**second.proposal.arguments, "metadata": {"value": APPROVED}}
    proposal = second.proposal.model_copy(update={"arguments": arguments})
    return plan.model_copy(
        update={"steps": (plan.steps[0], second.model_copy(update={"proposal": proposal}))}
    )


def _single_kernel(make_kernel: MakeKernel, mode: str) -> Kernel:
    features = ON if mode == "on" else Features()
    return make_kernel(features=features, driver=MetadataDriver())


def _executed(k: Kernel) -> list[dict[str, Any]]:
    """Record the arguments of every provider call."""
    calls: list[dict[str, Any]] = []
    execute = k.backend.execute

    async def recording(ctx: Any, binding: Any, action: Any, attempt: int) -> Any:
        calls.append(copy.deepcopy(action.arguments))
        return await execute(ctx, binding, action, attempt)

    k.backend.execute = recording  # type: ignore[method-assign]
    return calls


def _mutating_validator(k: Kernel) -> dict[str, bool]:
    """A validator that, once armed, rewrites the nested ``metadata`` value it is given."""
    armed = {"on": False}
    validate = k.validator.validate

    async def mutating(ctx: Any, item: Any) -> Any:
        meta = item.proposal.arguments.get("metadata")
        if armed["on"] and isinstance(meta, dict):
            meta["value"] = MUTATED
        return await validate(ctx, item)

    k.validator.validate = mutating  # type: ignore[method-assign]
    return armed


def _mutate_after_staleness(k: Kernel) -> None:
    """The action's nested arguments change after its revalidation, as a plugin holding a
    reference to them would change them (the path C-3 (i) closes)."""
    staleness = k.coordinator._staleness

    async def then_mutate(cont: Any, action: Any) -> Any:
        reason = await staleness(cont, action)
        meta = action.arguments.get("metadata")
        if isinstance(meta, dict):
            meta["value"] = MUTATED
        return reason

    k.coordinator._staleness = then_mutate  # type: ignore[method-assign]


@pytest.mark.parametrize("mode", ["off", "on"])
async def test_validator_mutation_never_reaches_a_single_action(
    make_kernel: MakeKernel, mode: str
) -> None:
    """Codex C-3 on the single-action path (shared with ``off``): a validator rewrites the
    nested arguments at dispatch-time revalidation. It changed its own copy only: the
    provider receives the approved values and the stored action keeps them."""
    k = _single_kernel(make_kernel, mode)
    calls = _executed(k)
    armed = _mutating_validator(k)
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    armed["on"] = True
    run = await _decide(k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    assert [c["metadata"]["value"] for c in calls] == [APPROVED]
    (action,) = await k.store.list_actions(TENANT, run.run_id)
    assert action.arguments["metadata"]["value"] == APPROVED


async def test_validator_mutation_never_reaches_a_plan_step(make_kernel: MakeKernel) -> None:
    """Codex C-3 on the plan path: the validator rewrites step 2's nested arguments at its
    revalidation, after the plan's approval. Step 2 runs with the approved values."""
    k = _plan_kernel(make_kernel, driver=NotesPlanDriver(plan=_metadata_plan()))
    calls = _executed(k)
    armed = _mutating_validator(k)
    run = await _start(k)
    armed["on"] = True
    run = await _decide(k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    assert calls[1]["metadata"]["value"] == APPROVED
    assert (await _actions(k, run.run_id))[1].arguments["metadata"]["value"] == APPROVED


@pytest.mark.parametrize("mode", ["off", "on"])
async def test_changed_arguments_block_a_single_action_before_reservation(
    make_kernel: MakeKernel, mode: str
) -> None:
    """C-3 (ii): the action's arguments change after approval by a path that bypasses the
    copy. The digest input of the action as it would be dispatched no longer matches the
    approval's digest: no reservation, no provider call, the action BLOCKED and the run
    FAILED STALE with ``KERNEL-ARGUMENTS-CHANGED``."""
    k = _single_kernel(make_kernel, mode)
    _mutate_after_staleness(k)
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    run = await _decide(k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.STALE)
    assert "KERNEL-ARGUMENTS-CHANGED" in await _rules(k, run.run_id)
    (action,) = await k.store.list_actions(TENANT, run.run_id)
    assert action.state is ActionState.BLOCKED
    assert await _of(k, run.run_id, RunEventType.ACTION_RESERVED) == []
    assert k.backend.create_calls == 0


async def test_changed_arguments_block_a_plan_step_before_reservation(
    make_kernel: MakeKernel,
) -> None:
    """C-3 (ii) on the plan path: step 2's resolved arguments change after its
    revalidation. Its dispatch input no longer matches its approved step input with the
    lineage substituted: step 2 BLOCKED before it reserves, the run FAILED STALE with the
    finding, step 1 committed and verified."""
    k = _plan_kernel(make_kernel, driver=NotesPlanDriver(plan=_metadata_plan()))
    _mutate_after_staleness(k)
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.STALE)
    assert "KERNEL-ARGUMENTS-CHANGED" in await _rules(k, run.run_id)
    first, second = await _actions(k, run.run_id)
    assert (first.state, second.state) == (ActionState.VERIFIED, ActionState.BLOCKED)
    reserved = [e.action_id for e in await _of(k, run.run_id, RunEventType.ACTION_RESERVED)]
    assert reserved == [first.action_id]
    assert k.backend.create_calls == 1
    assert await _step_statuses(k, run.run_id) == ["verified", "unstarted"]
