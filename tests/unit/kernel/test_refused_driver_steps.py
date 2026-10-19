"""Driver reads and proposals the kernel refuses for a reason other than the connection
(Task 2c.8c round 2).

Each of these raised out of the driver turn and left the run RUNNING with nothing queued:
a read the policy refuses (the requester role is missing), a read of an unknown capability, a
write capability requested as a read, and a proposal that is neither a write nor an answer.
Now a read is refused to the driver as a rejected read, with a fixed code per cause and a
fixed message that names no role, credential, subject or policy detail; the refused read never
reaches the provider (PR-26), and a driver that keeps asking ends the run FAILED
``BUDGET_EXHAUSTED``. A proposal of such a kind is the fixed ``KERNEL-PROPOSAL-KIND`` repair
finding. Each test runs ``off`` and ``on``; both stores run through `run_store`.
"""

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from e_agent.contracts.context import TaskContext
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import TERMINAL_RUN_STATES, ReasonCode, RunState
from e_agent.kernel.errors import KernelError
from e_agent.kernel.gateway import (
    NOT_A_READ,
    OUTSIDE_TASK,
    READ_NOT_PERMITTED,
    READ_REFUSALS,
    UNKNOWN_CAPABILITY,
)
from e_agent.sdk.ports import (
    DriverInput,
    DriverStep,
    FinalAnswer,
    ProposeAction,
    ReadRequest,
    RequestReads,
)

from .conftest import CONN, CREATE, NOTES_TASK, READ, TENANT, Kernel, principal

MakeKernel = Callable[..., Kernel]
MODES = ["off", "on"]
UNKNOWN = "notes.unknown.read.v1"
READ_CASES = ["not-permitted", "unknown", "write-as-read"]
PROPOSAL_CASES = ["unknown", "read"]
SECRETS = ("requester", "role", "policy", "svc", "secret", "credential", "dave")
"""Words a refusal must never carry: the missing role, the policy, the subject, the actor."""


def _read_contract(case: str) -> str:
    return {"not-permitted": READ.contract_id, "unknown": UNKNOWN}.get(case, CREATE.contract_id)


def _expected_code(mode: str, case: str) -> str:
    """In ``on`` an unknown capability is outside the run's tool set and refused as such
    first (D6); every other case gets its own code in both modes."""
    if case == "unknown" and mode == "on":
        return OUTSIDE_TASK
    return {"not-permitted": READ_NOT_PERMITTED, "unknown": UNKNOWN_CAPABILITY}.get(
        case, NOT_A_READ
    )


def _kernel(make_kernel: MakeKernel, mode: str, driver: Any) -> Kernel:
    features = Features(execution_ir=FeatureMode.ON) if mode == "on" else Features()
    return make_kernel(features=features, driver=driver)


async def _start(k: Kernel, mode: str, case: str, run_id: str | None = None) -> Any:
    """``not-permitted`` is started by a principal without the requester role, which the
    default policy refuses every read (`DefaultPolicy`); start_run itself checks no role."""
    actor = principal("dave", set()) if case == "not-permitted" else k.requester
    task_kind = NOTES_TASK.task_id if mode == "on" else None
    return await k.coordinator.start_run(
        actor, "write standup note", k.scope, run_id=run_id, task_kind=task_kind
    )


@dataclass
class ReadsThenProposes:
    """Reads ``contracts`` in turn (the last one repeats) until it observes something, then
    proposes ``proposals`` in turn (the last one repeats); answers after a verified result."""

    contracts: tuple[str, ...] = (READ.contract_id,)
    proposals: tuple[str, ...] = (CREATE.contract_id,)
    driver_id: str = "notes-refused-steps-driver"
    reads: int = 0
    proposed: int = 0
    seen: list[DriverInput] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.seen.append(step_input)
        if step_input.action_result is not None:
            return FinalAnswer(text="done")
        if not step_input.observations:
            contract = self.contracts[min(self.reads, len(self.contracts) - 1)]
            self.reads += 1
            request = ReadRequest(
                request_id=f"r{self.reads}", contract_id=contract, connection_id=CONN, arguments={}
            )
            return RequestReads(reads=(request,))
        contract = self.proposals[min(self.proposed, len(self.proposals) - 1)]
        self.proposed += 1
        return ProposeAction(
            proposal=ActionProposal(
                contract_id=contract, connection_id=CONN, arguments={"text": "notes"}
            )
        )


async def _events(k: Kernel, run_id: str, kind: RunEventType) -> list[Any]:
    return [e for e in await k.store.list_events(TENANT, run_id) if e.type is kind]


async def _rules(k: Kernel, run_id: str) -> set[str]:
    return {
        f["rule_id"]
        for e in await _events(k, run_id, RunEventType.VALIDATION_COMPLETED)
        for f in e.payload.get("findings", [])
    }


async def _awaits_something(k: Kernel, run_id: str) -> None:
    """Liveness (ruling 3): terminal, or pending work, or a pending approval."""
    run = await k.store.get_run(TENANT, run_id)
    assert (
        run.state in TERMINAL_RUN_STATES
        or run.state is RunState.WAITING_APPROVAL
        or await k.store.has_pending_work(TENANT, run_id)
    ), (run.state, run.reason)


# -- reads ---------------------------------------------------------------------------------
@pytest.mark.parametrize("case", READ_CASES)
@pytest.mark.parametrize("mode", MODES)
async def test_refused_read_fails_closed(make_kernel: MakeKernel, mode: str, case: str) -> None:
    """The read is refused to the driver with its cause's fixed code and message, never let
    through to the provider; a driver that keeps asking ends FAILED ``BUDGET_EXHAUSTED``."""
    driver = ReadsThenProposes(contracts=(_read_contract(case),))
    k = _kernel(make_kernel, mode, driver)
    run = await _start(k, mode, case)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.BUDGET_EXHAUSTED)
    assert k.backend.read_calls == 0 and k.backend.create_calls == 0
    code = _expected_code(mode, case)
    rejected = await _events(k, run.run_id, RunEventType.READ_REJECTED)
    assert len(rejected) == driver.reads > 1
    assert {e.payload["code"] for e in rejected} == {code}
    told = {m for step_input in driver.seen for m in step_input.read_errors.values()}
    assert len(told) == 1
    if code != OUTSIDE_TASK:
        assert told == {f"{code}: {READ_REFUSALS[code]}"}
    assert not any(word in m.lower() for m in told for word in SECRETS)
    assert not await _events(k, run.run_id, RunEventType.READ_RECORDED)
    assert await k.store.list_unfinished_runs() == []


@pytest.mark.parametrize("case", ["unknown", "write-as-read"])
@pytest.mark.parametrize("mode", MODES)
async def test_a_refused_read_of_the_wrong_capability_lets_the_driver_recover(
    make_kernel: MakeKernel, mode: str, case: str
) -> None:
    """The refusal is feedback: a driver that reads the right capability next proposes, and
    the run waits for approval as it would have."""
    driver = ReadsThenProposes(contracts=(_read_contract(case), READ.contract_id))
    k = _kernel(make_kernel, mode, driver)
    run = await _start(k, mode, case)
    assert run.state is RunState.WAITING_APPROVAL
    assert k.backend.read_calls == 1
    assert len(await _events(k, run.run_id, RunEventType.READ_REJECTED)) == 1


# -- proposals -----------------------------------------------------------------------------
@pytest.mark.parametrize("case", PROPOSAL_CASES)
@pytest.mark.parametrize("mode", MODES)
async def test_proposal_of_an_unknown_kind_is_a_repair_finding(
    make_kernel: MakeKernel, mode: str, case: str
) -> None:
    """A proposal for an unknown capability, or for a read, is a fixed repair finding: no
    action, nothing sent, and the repair budget ends the run FAILED ``VALIDATION_FAILED``.
    In ``on`` an unknown capability is outside the tool set and refused as such (D6)."""
    contract = UNKNOWN if case == "unknown" else READ.contract_id
    k = _kernel(make_kernel, mode, ReadsThenProposes(proposals=(contract,)))
    run = await _start(k, mode, "proposal")
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VALIDATION_FAILED)
    expected = (
        "KERNEL-PLAN-CAPABILITY" if (mode, case) == ("on", "unknown") else "KERNEL-PROPOSAL-KIND"
    )
    assert expected in await _rules(k, run.run_id)
    assert await k.store.list_actions(TENANT, run.run_id) == []
    assert k.backend.create_calls == 0
    assert await k.store.list_unfinished_runs() == []


@pytest.mark.parametrize("mode", MODES)
async def test_a_refused_proposal_kind_lets_the_driver_recover(
    make_kernel: MakeKernel, mode: str
) -> None:
    driver = ReadsThenProposes(proposals=(READ.contract_id, CREATE.contract_id))
    k = _kernel(make_kernel, mode, driver)
    run = await _start(k, mode, "proposal")
    assert run.state is RunState.WAITING_APPROVAL
    assert "KERNEL-PROPOSAL-KIND" in await _rules(k, run.run_id)


# -- liveness ------------------------------------------------------------------------------
STEPS = [
    *(f"read:{case}" for case in READ_CASES),
    *(f"propose:{case}" for case in PROPOSAL_CASES),
]


@pytest.mark.parametrize("then", ["retries", "recovers"])
@pytest.mark.parametrize("step", STEPS)
@pytest.mark.parametrize("mode", MODES)
async def test_no_run_left_non_terminal_after_a_refused_read_or_proposal(
    make_kernel: MakeKernel, mode: str, step: str, then: str
) -> None:
    """The sibling of `test_no_run_left_non_terminal_after_a_forbidden_read` for every other
    refused driver step: whether the driver asks again or recovers, the run is terminal, has
    pending work, or waits for approval. The exception the base code raised, which left the
    run RUNNING with nothing queued, is suppressed so that the invariant decides."""
    kind, case = step.split(":")
    if kind == "read":
        bad = (_read_contract(case),)
        driver = ReadsThenProposes(contracts=bad if then == "retries" else (*bad, READ.contract_id))
    else:
        bad = (UNKNOWN if case == "unknown" else READ.contract_id,)
        good = bad if then == "retries" else (*bad, CREATE.contract_id)
        driver = ReadsThenProposes(proposals=good)
    k = _kernel(make_kernel, mode, driver)
    run_id = f"run-{mode}-{kind}-{case}-{then}"
    with contextlib.suppress(KernelError):  # the base code raised; the invariant decides
        await _start(k, mode, case if kind == "read" else "proposal", run_id=run_id)
    await _awaits_something(k, run_id)
    assert k.backend.create_calls == 0
