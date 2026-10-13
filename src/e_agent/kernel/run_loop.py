"""Driver stepping, input handling and budgets (Phase 1 split of coordinator.py)."""

from __future__ import annotations

from functools import partial

from e_agent.contracts.action import ActionState
from e_agent.contracts.context import Principal
from e_agent.contracts.digest import digest
from e_agent.contracts.events import RunEventType
from e_agent.contracts.run import (
    ReasonCode,
    RunRecord,
    RunState,
)
from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.sdk.errors import AUTH_REQUIRED, DriverBudgetExceeded, KnownNoEffectError
from e_agent.sdk.ports import (
    AskClarification,
    DriverInput,
    FinalAnswer,
    ProposeAction,
    RequestReads,
)

from .continuation import ContinuationMixin
from .errors import ErrorCode, KernelError


class RunLoopMixin(ContinuationMixin):
    # ---------------------------------------------------------------- driving
    async def _drive(self, run: RunRecord, step_input: DriverInput) -> RunRecord:
        cont = await self._load_cont(run.tenant_id, run.run_id)
        ctx = cont.ctx
        while True:
            if cont.turns >= ctx.budgets.max_driver_turns:
                return await self._exhausted(run, "driver turns")
            cont.turns += 1
            tokens_used = getattr(self._driver, "tokens_used", lambda _: 0)(ctx.run_id)
            if tokens_used >= ctx.budgets.max_model_tokens:
                return await self._exhausted(run, "model tokens")
            try:
                step = await self._timed(
                    cont,
                    partial(self._driver.advance, ctx, step_input),
                    ctx.budgets.model_timeout_seconds,
                )
            except DriverBudgetExceeded:
                return await self._exhausted(run, "model usage")
            except TimeoutError:
                return await self._exhausted(run, "active time or model deadline")

            if (
                getattr(self._driver, "tokens_used", lambda _: 0)(ctx.run_id)
                >= ctx.budgets.max_model_tokens
            ):
                return await self._exhausted(run, "model tokens")
            if isinstance(step, RequestReads):
                for request in step.reads:
                    if cont.read_calls >= ctx.budgets.max_read_calls:
                        return await self._exhausted(run, "read calls")
                    try:
                        obs = await self._gateway_read(cont, request, count_budget=True)
                    except TimeoutError:
                        return await self._exhausted(run, "active time or provider deadline")
                    except KnownNoEffectError as exc:
                        if exc.code == AUTH_REQUIRED:
                            # Credentials are not something the model can fix: fail, no feedback.
                            run = await self._store.get_run(run.tenant_id, run.run_id)
                            return await self._set_run_state(
                                run,
                                RunState.FAILED,
                                "provider authentication required",
                                code=ReasonCode.PROVIDER_ERROR,
                            )
                        await self._record_rejected_read(cont, request, exc)
                        continue
                    cont.reads[request.request_id] = request
                    cont.observations[request.request_id] = obs
                    cont.read_errors.pop(request.request_id, None)
                await self._persist(run.run_id)
                step_input = DriverInput(
                    task=run.task,
                    observations=tuple(cont.observations.values()),
                    read_errors=dict(cont.read_errors),
                )
                continue

            if isinstance(step, ProposeAction):
                run = await self._store.get_run(run.tenant_id, run.run_id)
                outcome = await self._handle_proposal(run, cont, step.proposal)
                if isinstance(outcome, RunRecord):
                    return outcome
                step_input = outcome
                continue

            if isinstance(step, AskClarification):
                run = await self._store.get_run(run.tenant_id, run.run_id)
                await self._store.update_run(
                    run.model_copy(update={"revision": run.revision + 1}),
                    run.revision,
                    [
                        (
                            RunEventType.INPUT_REQUESTED,
                            {"question": step.question, "kind": "clarification"},
                            None,
                        )
                    ],
                )
                run = await self._store.get_run(run.tenant_id, run.run_id)
                return await self._set_run_state(run, RunState.WAITING_INPUT)

            if isinstance(step, FinalAnswer):
                run = await self._store.get_run(run.tenant_id, run.run_id)
                # Ruling 3 (ADR 0022): a plain reply is only conversational when the run has
                # made no reads, read attempts (read_calls counts successes and rejections and
                # is never decremented) or proposals. Anything else is an unverified claim.
                conversational = (
                    cont.read_calls == 0
                    and not cont.reads
                    and not cont.read_errors
                    and cont.last_action_id is None
                    and cont.pending_action_id is None
                )
                if conversational:
                    # Crash-replay guard: counters live in the continuation, the ledger is durable.
                    worked = {
                        RunEventType.READ_RECORDED,
                        RunEventType.READ_REJECTED,
                        RunEventType.PROPOSAL_CREATED,
                    }
                    conversational = not any(
                        e.type in worked
                        for e in await self._store.list_events(run.tenant_id, run.run_id)
                    )
                if conversational:
                    await self._store.update_run(
                        run.model_copy(update={"revision": run.revision + 1}),
                        run.revision,
                        [
                            (
                                RunEventType.INPUT_REQUESTED,
                                {"question": step.text, "kind": "reply"},
                                None,
                            )
                        ],
                    )
                    run = await self._store.get_run(run.tenant_id, run.run_id)
                    return await self._set_run_state(run, RunState.WAITING_INPUT)
                last_action = (
                    await self._store.get_action(run.tenant_id, cont.last_action_id)
                    if cont.last_action_id
                    else None
                )
                if cont.pending_action_id is None and (
                    last_action is None or last_action.state is not ActionState.VERIFIED
                ):
                    if cont.repairs >= ctx.budgets.max_validation_repairs:
                        return await self._set_run_state(
                            run,
                            RunState.FAILED,
                            "no independently verified outcome",
                            code=ReasonCode.VERIFICATION_FAILED,
                        )
                    cont.repairs += 1
                    await self._persist(run.run_id)
                    repair_finding = Finding(
                        rule_id="KERNEL-VERIFICATION",
                        rule_version="1",
                        status=ValidationStatus.FAIL,
                        message=(
                            "Plain text cannot complete this task. "
                            "Propose a structured answer "
                            "for independent verification, propose the requested action, "
                            "or request clarification for missing user details."
                        ),
                    )
                    await self._store.update_run(
                        run.model_copy(update={"revision": run.revision + 1}),
                        run.revision,
                        [
                            (
                                RunEventType.VALIDATION_COMPLETED,
                                {
                                    "status": "FAIL",
                                    "findings": [repair_finding.model_dump(mode="json")],
                                },
                                None,
                            )
                        ],
                    )
                    run = await self._store.get_run(run.tenant_id, run.run_id)
                    step_input = DriverInput(
                        task=run.task,
                        observations=tuple(cont.observations.values()),
                        findings=(repair_finding,),
                    )
                    continue
                run = await self._store.update_run(
                    run.model_copy(update={"revision": run.revision + 1}),
                    run.revision,
                    [(RunEventType.MESSAGE_FINAL, {"text": step.text}, None)],
                )
                if cont.pending_action_id is None:
                    return await self._set_run_state(
                        run, RunState.SUCCEEDED, "answered", code=ReasonCode.ANSWERED
                    )
                return run
            raise KernelError(ErrorCode.INVALID_REQUEST, "driver returned an unknown step")

    async def accept_input(
        self,
        actor: Principal,
        run_id: str,
        text: str,
        expected_revision: int,
        *,
        enqueue: bool = False,
    ) -> RunRecord:
        """Resume the requester's persisted run; input grants no additional authority."""
        run = await self._store.get_run(actor.tenant_id, run_id)
        if actor.principal_id != run.requester_id:
            raise KernelError(ErrorCode.FORBIDDEN, "only the requester may answer")
        if run.revision != expected_revision or run.state is not RunState.WAITING_INPUT:
            raise KernelError(ErrorCode.CONFLICT, "input does not match the pending question")
        if not text.strip() or len(text) > 4000:
            raise KernelError(ErrorCode.INVALID_REQUEST, "input must contain 1..4000 characters")
        await self._load_cont(actor.tenant_id, run_id)
        self._check_run_transition(run, RunState.RUNNING)
        run = await self._store.update_run(
            run.model_copy(
                update={
                    "revision": run.revision + 1,
                    "state": RunState.RUNNING,
                    "reason": None,
                    "reason_code": None,
                }
            ),
            run.revision,
            [
                (
                    RunEventType.INPUT_RECEIVED,
                    {"input": text, "expected_revision": expected_revision},
                    None,
                ),
                (RunEventType.RUN_STATE_CHANGED, {"state": RunState.RUNNING}, None),
            ],
            continuation=self._snapshot(run_id),
            work=("input", {}, digest({"revision": str(expected_revision), "input": text}))
            if enqueue
            else None,
        )
        return run

    async def continue_input(self, tenant_id: str, run_id: str) -> RunRecord:
        run = await self._store.get_run(tenant_id, run_id)
        if run.state is not RunState.RUNNING:
            raise KernelError(ErrorCode.CONFLICT, "run is no longer awaiting input work")
        events = await self._store.list_events(tenant_id, run_id)
        received = [e for e in events if e.type is RunEventType.INPUT_RECEIVED]
        if not received:
            raise KernelError(ErrorCode.CONFLICT, "no accepted input")
        cont = await self._load_cont(tenant_id, run_id)
        return await self._drive(
            run,
            DriverInput(
                task=run.task,
                user_input=str(received[-1].payload["input"]),
                observations=tuple(cont.observations.values()),
                read_errors=dict(cont.read_errors),
            ),
        )

    async def resume_input(
        self,
        actor: Principal,
        run_id: str,
        text: str,
        expected_revision: int,
    ) -> RunRecord:
        await self.accept_input(actor, run_id, text, expected_revision)
        return await self.continue_input(actor.tenant_id, run_id)

    async def _exhausted(self, run: RunRecord, what: str) -> RunRecord:
        run = await self._store.get_run(run.tenant_id, run.run_id)
        run = await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [(RunEventType.BUDGET_EXHAUSTED, {"budget": what}, None)],
        )
        return await self._set_run_state(
            run, RunState.FAILED, f"budget exhausted: {what}", code=ReasonCode.BUDGET_EXHAUSTED
        )
