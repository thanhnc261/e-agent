"""A driver read, or an answer proposal, on a connection the run cannot use (Task 2c.8c).

2c.8b made a write proposal or plan step on such a connection the fixed ``KERNEL-CONNECTION``
repair finding. A read and an answer raised FORBIDDEN (or DEPENDENCY_UNAVAILABLE) out of the
driver turn instead, leaving the run RUNNING with nothing queued until startup recovery,
which then classified it INTERRUPTED. Now:

- a read is refused to the driver as a rejected read with one fixed, non-secret code and
  message, whatever made the connection unusable, so the model can recover within its turn
  budget and the run otherwise ends terminal through the existing budget path;
- an answer is the ``KERNEL-CONNECTION`` repair finding, as a write proposal is;
- an answer whose capability has no verifier ends FAILED at once (``KERNEL-VERIFIER``).

Each test runs ``off`` and ``on``; both stores run through `run_store` (ENG-STORE-1).
"""

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from e_agent.contracts.connection import (
    ConnectionDescriptor,
    ConnectionOwnership,
    ConnectionStatus,
)
from e_agent.contracts.context import TaskContext
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import TERMINAL_RUN_STATES, ReasonCode, RunState
from e_agent.contracts.task import AcceptanceSpec
from e_agent.kernel.errors import KernelError
from e_agent.kernel.gateway import NO_READ_CONNECTION, UNUSABLE_CONNECTION
from e_agent.sdk.ports import (
    DriverInput,
    DriverStep,
    FinalAnswer,
    ProposeAction,
    ReadRequest,
    RequestReads,
)

from .conftest import BINDINGS, CONN, CREATE, NOTES_TASK, READ, SUMMARY, TENANT, Kernel

MakeKernel = Callable[..., Kernel]
OTHER = "conn-other"
MODES = ["off", "on"]
READ_KINDS = ["absent", "out-of-scope", "unbound", "disabled", "other-owner"]
"""Each way a read's connection is unusable: no such connection, one outside the run's scope,
one in scope without a binding for the capability, a disabled one, and another user's."""
ANSWER_KINDS = ["absent", "out-of-scope", "disabled", "other-owner"]
"""As for reads, less ``unbound``: an answer has no binding of its own."""
ANSWER_TASK = NOTES_TASK.model_copy(
    update={
        "capabilities": (*NOTES_TASK.capabilities, SUMMARY.contract_id),
        "acceptance": AcceptanceSpec(required_answer=SUMMARY.contract_id),
    }
)
REFUSAL = f"{UNUSABLE_CONNECTION}: {NO_READ_CONNECTION}"
"""What the driver is told: the same for every kind, so it reveals nothing about which."""
SECRETS = ("svc", "carol", "secret", "credential")
"""The connections' provider subjects and owner, and words a refusal must never carry."""


def _connection(conn: str, kind: str) -> ConnectionDescriptor:
    delegated = conn == OTHER and kind == "other-owner"
    return ConnectionDescriptor(
        tenant_id=TENANT,
        connection_id=conn,
        version=1,
        integration_id="notes-mem",
        ownership=(
            ConnectionOwnership.USER_DELEGATED if delegated else ConnectionOwnership.TENANT_SHARED
        ),
        owner_principal="carol" if delegated else None,
        provider_subject="carol@notes" if delegated else "svc",
        status=(
            ConnectionStatus.DISABLED
            if conn == OTHER and kind == "disabled"
            else ConnectionStatus.ACTIVE
        ),
    )


def _kernel(make_kernel: MakeKernel, mode: str, kind: str, driver: Any, **kw: Any) -> Kernel:
    """A kernel whose ``OTHER`` connection is unusable for the run in the way ``kind`` names;
    ``CONN`` stays usable. Every binding covers ``OTHER`` unless ``kind`` is ``unbound``."""
    features = Features(execution_ir=FeatureMode.ON) if mode == "on" else Features()
    connections = [_connection(CONN, kind)]
    if kind != "absent":
        connections.append(_connection(OTHER, kind))
    bound = (CONN,) if kind == "unbound" else (CONN, OTHER)
    return make_kernel(
        features=features,
        driver=driver,
        connections=connections,
        binding_connections={b.binding_id: bound for b in BINDINGS},
        **kw,
    )


def _scope(k: Kernel, kind: str) -> frozenset[str]:
    return k.scope if kind == "out-of-scope" else k.scope | {OTHER}


async def _start(k: Kernel, mode: str, kind: str, run_id: str | None = None) -> Any:
    task_kind = NOTES_TASK.task_id if mode == "on" else None
    return await k.coordinator.start_run(
        k.requester, "write standup note", _scope(k, kind), run_id=run_id, task_kind=task_kind
    )


@dataclass
class ReadingDriver:
    """Reads on each of ``connections`` in turn (the last one repeats) until it observes
    something, then proposes one note on ``CONN``; answers after the verified result."""

    connections: tuple[str, ...]
    driver_id: str = "notes-reading-driver"
    reads: int = 0
    seen: list[DriverInput] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.seen.append(step_input)
        if step_input.action_result is not None:
            return FinalAnswer(text="done")
        if not step_input.observations:
            conn = self.connections[min(self.reads, len(self.connections) - 1)]
            self.reads += 1
            request = ReadRequest(
                request_id=f"r{self.reads}",
                contract_id=READ.contract_id,
                connection_id=conn,
                arguments={},
            )
            return RequestReads(reads=(request,))
        return ProposeAction(
            proposal=ActionProposal(
                contract_id=CREATE.contract_id, connection_id=CONN, arguments={"text": "notes"}
            )
        )


@dataclass
class AnsweringDriver:
    """Reads on ``CONN``, then proposes the notes answer on ``answer_on``."""

    answer_on: str
    driver_id: str = "notes-answering-driver"
    seen: list[DriverInput] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.seen.append(step_input)
        if step_input.action_result is not None:
            return FinalAnswer(text="done")
        if not step_input.observations:
            request = ReadRequest(
                request_id="r1", contract_id=READ.contract_id, connection_id=CONN, arguments={}
            )
            return RequestReads(reads=(request,))
        count = step_input.observations[0].data["count"]
        return ProposeAction(
            proposal=ActionProposal(
                contract_id=SUMMARY.contract_id,
                connection_id=self.answer_on,
                arguments={"count": str(count)},
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


async def _nothing_left(k: Kernel, run_id: str) -> None:
    """Liveness (ruling 3): terminal, or pending work, or a pending approval."""
    run = await k.store.get_run(TENANT, run_id)
    assert (
        run.state in TERMINAL_RUN_STATES
        or run.state is RunState.WAITING_APPROVAL
        or await k.store.has_pending_work(TENANT, run_id)
    ), (run.state, run.reason)
    if run.state is not RunState.WAITING_APPROVAL:
        assert await k.store.list_unfinished_runs() == []


def _answer_verifier(k: Kernel) -> Any:
    return k.coordinator._registry.verifier_for(SUMMARY.contract_id)


# -- reads ---------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", READ_KINDS)
@pytest.mark.parametrize("mode", MODES)
async def test_read_on_unusable_connection_fails_closed(
    make_kernel: MakeKernel, mode: str, kind: str
) -> None:
    """The gateway refuses the read before any provider call and tells the driver, with one
    fixed message that names no connection state or secret. A driver that keeps asking spends
    its budget, and the run ends FAILED ``BUDGET_EXHAUSTED``, never an exception that strands
    it RUNNING."""
    driver = ReadingDriver(connections=(OTHER,))
    k = _kernel(make_kernel, mode, kind, driver)
    run = await _start(k, mode, kind)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.BUDGET_EXHAUSTED)
    assert k.backend.read_calls == 0 and k.backend.create_calls == 0
    rejected = await _events(k, run.run_id, RunEventType.READ_REJECTED)
    assert len(rejected) == driver.reads > 1
    assert {(e.payload["code"], e.payload["message"]) for e in rejected} == {
        (UNUSABLE_CONNECTION, NO_READ_CONNECTION)
    }
    told = {m for step_input in driver.seen for m in step_input.read_errors.values()}
    assert told == {REFUSAL}
    assert not any(word in REFUSAL.lower() for word in SECRETS)
    assert await k.store.list_actions(TENANT, run.run_id) == []
    await _nothing_left(k, run.run_id)


@pytest.mark.parametrize("mode", MODES)
async def test_a_refused_read_lets_the_driver_recover(make_kernel: MakeKernel, mode: str) -> None:
    """The refusal is feedback, not a failure: a driver that reads on the usable connection
    next goes on to propose, and the run waits for approval as it would have."""
    driver = ReadingDriver(connections=(OTHER, CONN))
    k = _kernel(make_kernel, mode, "out-of-scope", driver)
    run = await _start(k, mode, "out-of-scope")
    assert run.state is RunState.WAITING_APPROVAL
    assert k.backend.read_calls == 1
    assert len(await _events(k, run.run_id, RunEventType.READ_REJECTED)) == 1


# -- answers -------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ANSWER_KINDS)
@pytest.mark.parametrize("mode", MODES)
async def test_answer_on_unusable_connection_fails_closed(
    make_kernel: MakeKernel, mode: str, kind: str
) -> None:
    """An answer proposal on such a connection is the fixed ``KERNEL-CONNECTION`` repair
    finding, as a write proposal is (2c.8b): no action, no verification, and the repair
    budget ends the run FAILED ``VALIDATION_FAILED``."""
    k = _kernel(
        make_kernel,
        mode,
        kind,
        AnsweringDriver(answer_on=OTHER),
        with_answer=True,
        task=ANSWER_TASK,
    )
    run = await _start(k, mode, kind)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VALIDATION_FAILED)
    assert "KERNEL-CONNECTION" in await _rules(k, run.run_id)
    assert await k.store.list_actions(TENANT, run.run_id) == []
    assert _answer_verifier(k).calls == 0
    await _nothing_left(k, run.run_id)


@pytest.mark.parametrize("mode", MODES)
async def test_answer_on_a_usable_connection_is_verified(
    make_kernel: MakeKernel, mode: str
) -> None:
    """The control for the test above: the same answer on ``CONN`` is verified and the run
    succeeds, so the refusal there comes from the connection alone."""
    k = _kernel(
        make_kernel,
        mode,
        "out-of-scope",
        AnsweringDriver(answer_on=CONN),
        with_answer=True,
        task=ANSWER_TASK,
    )
    run = await _start(k, mode, "out-of-scope")
    assert run.state is RunState.SUCCEEDED, (run.state, run.reason)
    assert _answer_verifier(k).calls == 1


@pytest.mark.parametrize("mode", MODES)
async def test_answer_without_a_verifier_fails_closed(make_kernel: MakeKernel, mode: str) -> None:
    """Phase review P-1: an answer whose capability has no verifier can never be verified.
    The run ends FAILED ``VERIFICATION_FAILED`` with the fixed ``KERNEL-VERIFIER`` finding,
    no action and no exception."""
    k = _kernel(
        make_kernel,
        mode,
        "out-of-scope",
        AnsweringDriver(answer_on=CONN),
        with_answer=True,
        answer_verifier=False,
        task=ANSWER_TASK,
    )
    run = await _start(k, mode, "out-of-scope")
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VERIFICATION_FAILED)
    assert "KERNEL-VERIFIER" in await _rules(k, run.run_id)
    assert await k.store.list_actions(TENANT, run.run_id) == []
    await _nothing_left(k, run.run_id)


# -- liveness ------------------------------------------------------------------------------
@pytest.mark.parametrize("then", ["retries", "recovers", "answers-on-it"])
@pytest.mark.parametrize("kind", ["absent", "out-of-scope", "unbound", "disabled"])
@pytest.mark.parametrize("mode", MODES)
async def test_no_run_left_non_terminal_after_a_forbidden_read(
    make_kernel: MakeKernel, mode: str, kind: str, then: str
) -> None:
    """Ruling 3: after a refused read, whatever the driver does next (asks again, reads on
    the usable connection, or answers on the refused connection), the run is terminal, has
    pending work, or waits for approval. Not terminal with nothing pending is a failure; so
    is the exception the base code raised, which left the run RUNNING with nothing queued."""
    if then == "answers-on-it":
        driver = _ReadThenAnswer(bad=OTHER)
        k = _kernel(make_kernel, mode, kind, driver, with_answer=True, task=ANSWER_TASK)
    else:
        reads = (OTHER,) if then == "retries" else (OTHER, CONN)
        k = _kernel(make_kernel, mode, kind, ReadingDriver(connections=reads))
    run_id = f"run-{mode}-{kind}-{then}"
    with contextlib.suppress(KernelError):  # the base code raised; the invariant decides
        await _start(k, mode, kind, run_id=run_id)
    await _nothing_left(k, run_id)
    assert await _events(k, run_id, RunEventType.READ_REJECTED)


@dataclass
class _ReadThenAnswer:
    """Reads on ``bad`` once, then on ``CONN``, then proposes the answer on ``bad``."""

    bad: str
    driver_id: str = "notes-read-then-answer"
    turns: int = 0

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.turns += 1
        if step_input.action_result is not None:
            return FinalAnswer(text="done")
        if not step_input.observations:
            conn = self.bad if self.turns == 1 else CONN
            request = ReadRequest(
                request_id=f"r{self.turns}",
                contract_id=READ.contract_id,
                connection_id=conn,
                arguments={},
            )
            return RequestReads(reads=(request,))
        return ProposeAction(
            proposal=ActionProposal(
                contract_id=SUMMARY.contract_id, connection_id=self.bad, arguments={"count": "0"}
            )
        )
