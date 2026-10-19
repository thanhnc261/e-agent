"""Proposal and answer handling and validation (Phase 1 split of coordinator.py)."""

from __future__ import annotations

import copy
from functools import partial
from typing import Any

from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.capability import CapabilityBinding, EffectKind
from e_agent.contracts.common import new_id
from e_agent.contracts.context import TaskContext
from e_agent.contracts.digest import CanonicalizationError
from e_agent.contracts.events import RunEventType
from e_agent.contracts.evidence import ApprovedFact, Completeness
from e_agent.contracts.outcome import OutcomeReport, OutcomeStatus
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import (
    ReasonCode,
    RunRecord,
    RunState,
)
from e_agent.contracts.step import StepRecord
from e_agent.contracts.validation import Finding, ValidationResult, ValidationStatus
from e_agent.sdk.ports import (
    DriverInput,
    ValidationInput,
)
from e_agent.sdk.store import EventSpec

from .approval import (
    compute_digest,
    digest_input,
    fact_digest,
)
from .context import KERNEL_RULE_PREFIX
from .continuation import _Continuation, _GatewayReader
from .errors import KernelError
from .ir import StepDigestContext
from .ir_on import IrOnMixin, _fixed
from .reconstruct import proposal_keys
from .verification import outcome_payload

EVIDENCE_BUNDLE, NO_VALIDATOR_BUNDLE, ERROR_BUNDLE = "kernel-evidence-v1", "none", "error"
SENTINEL_BUNDLES = frozenset({EVIDENCE_BUNDLE, NO_VALIDATOR_BUNDLE, ERROR_BUNDLE})
"""The rule bundle versions `_validate` reports when no domain rule ran: incomplete
evidence, no validator, a validator that raised or claimed a kernel rule id. None is a
real bundle to bind."""
PROPOSAL_KIND = "The proposed capability is not a write or an answer this run can use."
"""The fixed message of the ``KERNEL-PROPOSAL-KIND`` repair finding (2c.8c round 2)."""
KERNEL_RULE_ID_CLAIMED = "validator returned a kernel rule id"
"""The fixed message when a validator's result claims a ``KERNEL-*`` rule id (review D3-10):
only the kernel authors those findings, whose text ADR 0032 §5 sends unmasked."""


def _validator_error(validator_id: str, message: str) -> ValidationResult:
    """A validator that failed or broke the kernel-id rule: the write is blocked (fail closed)."""
    finding = Finding(
        rule_id="KERNEL-VALIDATOR-ERROR",
        rule_version="1",
        status=ValidationStatus.ERROR,
        message=message,
    )
    return ValidationResult(
        status=ValidationStatus.ERROR,
        findings=(finding,),
        rule_bundle_version=ERROR_BUNDLE,
        validator_id=validator_id,
    )


class ProposalsMixin(IrOnMixin):
    # ------------------------------------------------------------- proposals
    async def _handle_proposal(
        self, run: RunRecord, cont: _Continuation, proposal: ActionProposal
    ) -> RunRecord | DriverInput:
        ctx = cont.ctx
        refused = await self._outside_task_set(run, cont, proposal)  # `on` only (D6)
        if refused is not None:
            return refused
        descriptor = self._registry.capabilities.get(proposal.contract_id)
        if descriptor is not None and descriptor.effect is EffectKind.ANSWER:
            return await self._handle_answer(run, cont, proposal)
        if descriptor is None or descriptor.effect is not EffectKind.WRITE:  # 2c.8c round 2
            kind = _fixed("KERNEL-PROPOSAL-KIND", PROPOSAL_KIND)
            return await self._repair_finding(run, cont, (kind,))
        if cont.writes >= ctx.budgets.max_admitted_writes:
            return await self._exhausted(run, "admitted writes")
        try:
            connection = self._connections.usable(ctx, proposal.connection_id)
            binding = self._registry.resolve(proposal.contract_id, proposal.connection_id)
        except KernelError:
            return await self._connection_refused(run, cont)
        decision = self._policy.evaluate(ctx, descriptor, proposal.connection_id)
        validation = await self._validate(ctx, cont, proposal, binding)

        credential_version = (
            await self._credentials.version(ctx, proposal.connection_id)
            if self._credentials
            else "none"
        )
        evidence = [cont.observations[r].evidence for r in sorted(cont.observations)]
        fact_digests = {
            o.evidence.evidence_id: fact_digest(o.data)
            for o in cont.observations.values()
            if o.evidence.revision is None
        }
        canonical = digest_input(
            tenant_id=ctx.tenant_id,
            requester_id=ctx.principal.principal_id,
            logical_operation_id=run.logical_operation_id,
            contract_id=proposal.contract_id,
            binding_id=binding.binding_id,
            connection_id=connection.connection_id,
            connection_version=connection.version,
            credential_subject=connection.credential_subject(),
            arguments=dict(proposal.arguments),
            expected_effects=proposal.expected_effects,
            evidence=evidence,
            rule_bundle_version=validation.rule_bundle_version,
            policy_version=decision.policy_version,
            credential_version=credential_version,
            fact_digests=fact_digests,
        )
        try:
            action_digest = compute_digest(canonical)
        except CanonicalizationError as exc:
            validation = ValidationResult(
                status=ValidationStatus.FAIL,
                findings=(
                    Finding(
                        rule_id="KERNEL-ARGS",
                        rule_version="1",
                        status=ValidationStatus.FAIL,
                        message=f"arguments outside the digest profile: {exc}",
                    ),
                ),
                rule_bundle_version=validation.rule_bundle_version,
                validator_id="kernel",
            )
            action_digest = "invalid"

        previous = cont.last_action_id
        action = ActionRecord(
            action_id=new_id("act"),
            tenant_id=ctx.tenant_id,
            run_id=run.run_id,
            logical_operation_id=run.logical_operation_id,
            contract_id=proposal.contract_id,
            binding_id=binding.binding_id,
            connection_id=connection.connection_id,
            connection_version=connection.version,
            credential_subject=connection.credential_subject(),
            credential_version=credential_version,
            approved_facts=tuple(
                ApprovedFact(contract_id=o.contract_id, data=dict(o.data), evidence=o.evidence)
                for o in cont.observations.values()
            ),
            arguments=dict(proposal.arguments),
            digest=action_digest,
            state=ActionState.PROPOSED,
            revision=1,
            supersedes_action_id=previous,
        )
        await self._store.put_action(
            action,
            None,
            [
                (
                    RunEventType.PROPOSAL_CREATED,
                    {
                        "contract_id": action.contract_id,
                        "arguments": action.arguments,
                        "supersedes": previous,
                        **proposal_keys(action),  # ADR 0031 §3
                    },
                    action.action_id,
                )
            ],
        )
        cont.last_action_id = action.action_id
        findings_payload = [f.model_dump(mode="json") for f in validation.findings]
        blocked = validation.blocks_write or not decision.permitted
        if blocked:
            action = await self._transition(
                action,
                ActionState.BLOCKED,
                (
                    RunEventType.VALIDATION_COMPLETED,
                    {
                        "status": validation.status,
                        "findings": findings_payload,
                        "policy_reasons": list(decision.reasons),
                    },
                ),
            )
            cont.pending_action_id = None
            if not decision.permitted:
                run = await self._store.get_run(run.tenant_id, run.run_id)
                return await self._set_run_state(
                    run, RunState.FAILED, "policy denied", code=ReasonCode.POLICY_DENIED
                )
            if cont.repairs >= ctx.budgets.max_validation_repairs:
                run = await self._store.get_run(run.tenant_id, run.run_id)
                return await self._set_run_state(
                    run, RunState.FAILED, "validation blocked", code=ReasonCode.VALIDATION_FAILED
                )
            cont.repairs += 1
            cont.findings = validation.findings
            return DriverInput(
                task=run.task,
                observations=tuple(cont.observations.values()),
                findings=validation.findings,
            )

        action = await self._transition(
            action,
            ActionState.VALIDATED,
            (
                RunEventType.VALIDATION_COMPLETED,
                {"status": validation.status, "findings": findings_payload},
            ),
        )
        shadow: list[EventSpec | StepRecord] = []  # execution IR (ADR 0027); `off` adds nothing
        if self._ir_shadow or self._ir_on:
            step_ctx = StepDigestContext(
                tenant_id=ctx.tenant_id,
                requester_id=ctx.principal.principal_id,
                binding_id=binding.binding_id,
                connection_version=connection.version,
                credential_subject=connection.credential_subject(),
                credential_version=credential_version,
                evidence=tuple(evidence),
                fact_digests=fact_digests,
                rule_bundle_version=validation.rule_bundle_version,
                policy_version=decision.policy_version,
            )
            if self._ir_shadow:
                shadow = list(await self._shadow_plan(run, cont, proposal, action, step_ctx))
            else:  # `on`: the action is linked to its stored 1-step plan, or falls back
                action, wait = await self._on_plan(run, cont, proposal, action, step_ctx)
                shadow = list(wait)
        return await self._await_approval(run, cont, action, canonical, validation, shadow)

    async def _await_approval(
        self,
        run: RunRecord,
        cont: _Continuation,
        action: ActionRecord,
        canonical: dict[str, Any],
        validation: ValidationResult,
        extra: list[EventSpec | StepRecord],
    ) -> RunRecord:
        """Checkpoint a VALIDATED action as the run's pending approval: the action, the run's
        WAITING_APPROVAL state, the continuation and ``extra`` with the approval request, in
        one write. ``canonical`` is the approval digest's input, shown verbatim."""
        cont.pending_action_id = action.action_id
        cont.canonical_proposal = canonical
        cont.last_validation = validation
        cont.approval_requested_at = self._clock()
        run = await self._store.get_run(run.tenant_id, run.run_id)
        self._check_run_transition(run, RunState.WAITING_APPROVAL)
        waiting = run.model_copy(
            update={
                "state": RunState.WAITING_APPROVAL,
                "revision": run.revision + 1,
                "reason": None,
                "reason_code": None,
            }
        )
        checkpoint = self._snapshot(run.run_id)
        assert checkpoint is not None
        await self._store.wait_for_approval(
            action.model_copy(
                update={"state": ActionState.AWAITING_APPROVAL, "revision": action.revision + 1}
            ),
            action.revision,
            waiting,
            run.revision,
            checkpoint,
            [
                *extra,
                (
                    RunEventType.APPROVAL_REQUESTED,
                    {
                        "digest": action.digest,
                        "expires_at": (
                            cont.approval_requested_at + self._ttl_for(run, cont)
                        ).isoformat(),
                        "plan_id": action.plan_id,  # the stored link (ADR 0031 §3)
                        "step_index": action.step_index,
                    },
                    action.action_id,
                ),
                (
                    RunEventType.RUN_STATE_CHANGED,
                    {
                        "from": run.state,
                        "to": RunState.WAITING_APPROVAL,
                        "reason": None,
                        "reason_code": None,
                    },
                    None,
                ),
            ],
        )
        return waiting

    async def _handle_answer(
        self, run: RunRecord, cont: _Continuation, proposal: ActionProposal
    ) -> RunRecord | DriverInput:
        """Structured answers: no approval or dispatch; the domain verifier recomputes
        the answer from fresh, independent reads."""
        ctx = cont.ctx
        try:  # as a write proposal: a repair finding, never an exception (2c.8c)
            connection = self._connections.usable(ctx, proposal.connection_id)
        except KernelError:
            return await self._connection_refused(run, cont)
        verifier = self._registry.verifier_for(proposal.contract_id)
        if verifier is None:  # it can never be verified: fail, never claim it (review P-1)
            return await self._no_verifier(run)
        try:
            action_digest = compute_digest(
                {"contract_id": proposal.contract_id, "arguments": dict(proposal.arguments)}
            )
        except CanonicalizationError:
            action_digest = "invalid"
        if cont.last_action_id is not None:
            previous = await self._store.get_action(ctx.tenant_id, cont.last_action_id)
            if (
                previous.state is ActionState.VERIFIED
                and previous.contract_id == proposal.contract_id
                and previous.connection_id == connection.connection_id
                and previous.digest == action_digest
                and previous.arguments == dict(proposal.arguments)
            ):
                return await self._finish_verified(
                    cont, (), "The structured answer was independently verified.", acknowledge=False
                )
        action = ActionRecord(
            action_id=new_id("act"),
            tenant_id=ctx.tenant_id,
            run_id=run.run_id,
            logical_operation_id=run.logical_operation_id,
            contract_id=proposal.contract_id,
            binding_id="answer",
            connection_id=connection.connection_id,
            connection_version=connection.version,
            credential_subject=connection.credential_subject(),
            arguments=dict(proposal.arguments),
            digest=action_digest,
            state=ActionState.PROPOSED,
            revision=1,
            supersedes_action_id=cont.last_action_id,
        )
        await self._store.put_action(
            action,
            None,
            [
                (
                    RunEventType.PROPOSAL_CREATED,
                    {
                        "contract_id": action.contract_id,
                        "arguments": action.arguments,
                        "kind": "answer",
                        "supersedes": cont.last_action_id,
                        **proposal_keys(action),
                    },
                    action.action_id,
                )
            ],
        )
        cont.last_action_id = action.action_id
        action = await self._transition(action, ActionState.VALIDATED)
        reader = _GatewayReader(self, cont, connection.connection_id)
        try:
            report = await verifier.verify(ctx, action, None, reader)
        except Exception as exc:  # verification unavailable: never claim the answer
            report = OutcomeReport(
                run_id=ctx.run_id,
                action_id=action.action_id,
                status=OutcomeStatus.UNKNOWN,
                checks=(),
                verifier_id=verifier.verifier_id,
                verifier_version=type(exc).__name__,
                reported_at=self._clock(),
            )
        report = self._kept(report)
        verified = report.status is OutcomeStatus.VERIFIED
        target = ActionState.VERIFIED if verified else ActionState.VERIFICATION_FAILED
        await self._store.record_outcome(
            ctx.tenant_id,
            report,
            action.model_copy(update={"state": target, "revision": action.revision + 1}),
            action.revision,
            [(RunEventType.OUTCOME_REPORTED, outcome_payload(report, target), action.action_id)],
        )
        if verified:
            return DriverInput(
                task=run.task,
                observations=tuple(cont.observations.values()),
                action_result={"status": "VERIFIED"},
            )
        run = await self._store.get_run(run.tenant_id, run.run_id)
        if cont.repairs >= ctx.budgets.max_validation_repairs:
            return await self._set_run_state(
                run, RunState.FAILED, "answer not verified", code=ReasonCode.VERIFICATION_FAILED
            )
        cont.repairs += 1
        findings = tuple(
            Finding(
                rule_id=f"VERIFY-{c.name}",
                rule_version="1",
                status=ValidationStatus.FAIL,
                message=f"answer check {c.name} failed",
                expected=c.expected,
                observed=c.observed,
            )
            for c in report.checks
            if not c.passed
        ) or (
            Finding(
                rule_id="VERIFY",
                rule_version="1",
                status=ValidationStatus.UNKNOWN,
                message="answer could not be verified",
            ),
        )
        return DriverInput(
            task=run.task, observations=tuple(cont.observations.values()), findings=findings
        )

    async def _validate(
        self,
        ctx: TaskContext,
        cont: _Continuation,
        proposal: ActionProposal,
        binding: CapabilityBinding,
    ) -> ValidationResult:
        if any(
            o.evidence.completeness is not Completeness.COMPLETE for o in cont.observations.values()
        ):
            return ValidationResult(
                status=ValidationStatus.UNKNOWN,
                findings=(
                    Finding(
                        rule_id="KERNEL-EVIDENCE",
                        rule_version="1",
                        status=ValidationStatus.UNKNOWN,
                        message="proposal evidence is incomplete",
                    ),
                ),
                rule_bundle_version=EVIDENCE_BUNDLE,
                validator_id="kernel",
            )
        validators = self._registry.validators_for(proposal.contract_id)
        if not validators:
            return ValidationResult(
                status=ValidationStatus.UNKNOWN,
                findings=(
                    Finding(
                        rule_id="KERNEL-NO-VALIDATOR",
                        rule_version="1",
                        status=ValidationStatus.UNKNOWN,
                        message="no validator registered for capability",
                    ),
                ),
                rule_bundle_version=NO_VALIDATOR_BUNDLE,
                validator_id="kernel",
            )
        item = ValidationInput(proposal=proposal, observations=tuple(cont.observations.values()))
        results: list[ValidationResult] = []
        for validator in validators:
            try:
                result = await self._timed(
                    cont,
                    # Each validator gets its own copy, never kernel-owned state: what it
                    # changes cannot reach an approved action (PR-08, PR-16, Codex C-3).
                    partial(validator.validate, ctx, copy.deepcopy(item)),
                    ctx.budgets.provider_timeout_seconds,
                )
            except Exception as exc:  # engine failure blocks the write (MVP §11)
                result = _validator_error(validator.validator_id, type(exc).__name__)
            else:
                if any(f.rule_id.startswith(KERNEL_RULE_PREFIX) for f in result.findings):
                    result = _validator_error(validator.validator_id, KERNEL_RULE_ID_CLAIMED)
            results.append(result)
        order = [ValidationStatus.ERROR, ValidationStatus.FAIL, ValidationStatus.UNKNOWN]
        status = next(
            (s for s in order if any(r.status is s for r in results)), ValidationStatus.PASS
        )
        return ValidationResult(
            status=status,
            findings=tuple(f for r in results for f in r.findings),
            rule_bundle_version="+".join(sorted(r.rule_bundle_version for r in results)),
            validator_id="+".join(sorted(r.validator_id for r in results)),
        )
