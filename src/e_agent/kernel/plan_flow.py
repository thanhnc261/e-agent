"""Multi-step action plans in execution IR ``on`` (Task 2c.7, ADR 0024, ADR 0025).

A driver's `ProposePlan` runs only in ``on``, in a run bound to its task definition whose
effective ``max_admitted_writes`` is above one; anywhere else it returns to the driver as a
fixed repair finding, never a fallback, because today's path cannot run it (target §6.4.8).
A 1-step plan is today's proposal.

- **Validate the whole plan before approval** (target §6.4.3): `validate_plan`, every step
  a write, each placeholder typed by its input schema, each step's connection, binding and
  policy, and the domain validation of every step without a placeholder. Every step's
  digest binds the rule bundle and policy versions known now; a placeholder step's domain
  validation of its resolved values runs before its reservation.
- **One approval** binds the plan digest (`plan.v1`, ADR 0024). The first step's action
  carries it and holds the approval; every step's action carries ``plan_id``,
  ``step_index``, the plan digest and its own logical operation id (`step_operation_id`).
- **Dispatch serially** inside the approval call (no background task, ENG-ARCH-7): step N + 1
  starts only after step N is VERIFIED (`_after_step_verified`). It resolves its lineage from
  the values the earlier step's verifier read back (``OutcomeReport.verified_values``, kept in
  the continuation's plan state), records them (``ir.lineage_resolved``, a validate step) and
  is revalidated like an approved action (`_dispatch`: facts, policy, connection,
  credential, rules, approval TTL) before it reserves. A rejection stops the plan; nothing
  committed is replayed and nothing falls back after the first reservation.
- Outside the approval call (recovery, reconciliation) a verified step never starts the
  next one: the run fails ``INTERRUPTED``. Resuming a plan and its partial-failure codes are
  Task 2c.8's.
"""

from __future__ import annotations

from typing import Any

from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.approval import ApprovalRecord
from e_agent.contracts.capability import EffectKind
from e_agent.contracts.common import new_id
from e_agent.contracts.digest import CanonicalizationError
from e_agent.contracts.events import RunEventType
from e_agent.contracts.evidence import ApprovedFact
from e_agent.contracts.plan import ActionPlan, encode_arguments
from e_agent.contracts.run import ReasonCode, RunRecord, RunState
from e_agent.contracts.step import StepKind, StepStatus
from e_agent.contracts.task import TaskDefinition
from e_agent.contracts.validation import Finding, ValidationResult, ValidationStatus
from e_agent.sdk.ports import DriverInput, PolicyDecision

from .approval import compute_digest, fact_digest
from .continuation import _Continuation, _PlanState
from .errors import ErrorCode, KernelError
from .ir import (
    LINEAGE_MESSAGES,
    LineageRejected,
    PlanValidationContext,
    StepDigestContext,
    has_placeholders,
    lineage_type_findings,
    plan_digest_input,
    resolve_lineage,
    validate_plan,
)
from .ir_on import OUTSIDE_SET, PLAN_INTERRUPTED, _fixed
from .proposals import ProposalsMixin

PLAN_UNSUPPORTED = "This run does not execute multi-step plans; propose one action."
ONE_WRITE = "This run admits one write; propose one action instead of a plan."
ANSWER_STEP = "A multi-step plan holds write steps only; propose an answer on its own."
PLAN_ARGS = "The plan's arguments are outside the digest profile."
"""The fixed messages of the plan refusals (no model text)."""


class PlanFlowMixin(ProposalsMixin):
    # -- proposal --------------------------------------------------------------------------
    async def _handle_plan(
        self, run: RunRecord, cont: _Continuation, plan: ActionPlan
    ) -> RunRecord | DriverInput:
        refusal = self._plan_refusal(run, cont)
        if refusal is not None:
            return await self._repair_finding(run, cont, (refusal,))
        if len(plan.steps) == 1:  # a 1-step plan is today's proposal (target §6.4.3)
            return await self._handle_proposal(run, cont, plan.steps[0].proposal)
        task = self._on_task(run, cont)
        assert task is not None  # `_plan_refusal` refused a run without its snapshot
        # The kernel owns the plan's identity: a fresh id, the run's admitted definition.
        plan = plan.model_copy(
            update={
                "plan_id": new_id("plan"),
                "task_id": task.task_id,
                "task_version": task.version,
            }
        )
        findings = self._plan_findings(plan, task, cont)
        if findings:
            return await self._repair_finding(run, cont, findings)
        built = await self._plan_contexts(run, cont, plan)
        if not isinstance(built, tuple):
            return built
        contexts, validation = built
        try:
            canonical = plan_digest_input(plan, contexts, run_operation_id=run.logical_operation_id)
            digest = compute_digest(canonical)
        except (CanonicalizationError, ValueError):  # `validate_plan` reports KERNEL-ARGS first
            return await self._repair_finding(run, cont, (_fixed("KERNEL-ARGS", PLAN_ARGS),))
        return await self._propose_plan(run, cont, plan, canonical, digest, validation)

    def _plan_refusal(self, run: RunRecord, cont: _Continuation) -> Finding | None:
        """The fixed finding for a run that cannot execute a plan, or None."""
        if not self._ir_on or run.task_id is None:  # `off`, `shadow`, or unresolved: `off`
            return _fixed("KERNEL-PLAN-UNSUPPORTED", PLAN_UNSUPPORTED)
        if self._on_task(run, cont) is None:  # a bound run without its snapshot fails closed
            return _fixed("KERNEL-PLAN-CAPABILITY", OUTSIDE_SET)
        if cont.ctx.budgets.max_admitted_writes <= 1:
            return _fixed("KERNEL-PLAN-WRITES", ONE_WRITE)
        return None

    def _plan_findings(
        self, plan: ActionPlan, task: TaskDefinition, cont: _Continuation
    ) -> tuple[Finding, ...]:
        """The pure checks of the whole plan: `validate_plan` against the writes the run has
        left, write steps only, and each placeholder typed by its step's input schema."""
        capabilities = self._registry.capabilities
        effects = {
            cid: capabilities[cid].effect for cid in task.capabilities if cid in capabilities
        }
        left = max(0, cont.ctx.budgets.max_admitted_writes - cont.writes)
        limits = PlanValidationContext(effects=effects, max_admitted_writes=left)
        findings = list(validate_plan(plan, task, limits))
        for step in plan.steps:
            descriptor = capabilities.get(step.proposal.contract_id)
            if descriptor is None:
                continue  # reported by `validate_plan`
            if descriptor.effect is EffectKind.ANSWER:
                findings.append(_fixed("KERNEL-PLAN-ANSWER-STEP", ANSWER_STEP))
            schema = self._registry.input_schemas.get(descriptor.input_schema_id)
            findings.extend(lineage_type_findings(step, schema))
        return tuple(findings)

    async def _plan_contexts(
        self, run: RunRecord, cont: _Continuation, plan: ActionPlan
    ) -> tuple[dict[str, StepDigestContext], ValidationResult] | RunRecord | DriverInput:
        """Each step's digest context: its connection, binding and policy now, and its domain
        validation unless a placeholder defers it. A denied policy fails the run, a blocking
        validation returns to the driver, as for a single proposal."""
        ctx = cont.ctx
        evidence = tuple(cont.observations[r].evidence for r in sorted(cont.observations))
        fact_digests = {
            o.evidence.evidence_id: fact_digest(o.data)
            for o in cont.observations.values()
            if o.evidence.revision is None
        }
        contexts: dict[str, StepDigestContext] = {}
        results: list[ValidationResult] = []
        for step in plan.steps:
            proposal = step.proposal
            descriptor = self._registry.descriptor(proposal.contract_id)
            connection = self._connections.usable(ctx, proposal.connection_id)
            binding = self._registry.resolve(proposal.contract_id, proposal.connection_id)
            decision = self._policy.evaluate(ctx, descriptor, proposal.connection_id)
            if not decision.permitted:
                return await self._plan_denied(run, decision)
            if has_placeholders(proposal):
                # Its values are domain-validated before it reserves; the digest binds the
                # rule bundle known now, read from the validators on its wire-form arguments.
                wire = proposal.model_copy(
                    update={"arguments": encode_arguments(proposal.arguments)}
                )
                rules = (await self._validate(ctx, cont, wire, binding)).rule_bundle_version
            else:
                validation = await self._validate(ctx, cont, proposal, binding)
                if validation.blocks_write:
                    cont.findings = validation.findings
                    return await self._repair_finding(run, cont, validation.findings)
                results.append(validation)
                rules = validation.rule_bundle_version
            credential_version = (
                await self._credentials.version(ctx, proposal.connection_id)
                if self._credentials
                else "none"
            )
            contexts[step.step_id] = StepDigestContext(
                tenant_id=ctx.tenant_id,
                requester_id=ctx.principal.principal_id,
                binding_id=binding.binding_id,
                connection_version=connection.version,
                credential_subject=connection.credential_subject(),
                credential_version=credential_version,
                evidence=evidence,
                fact_digests=fact_digests,
                rule_bundle_version=rules,
                policy_version=decision.policy_version,
            )
        merged = ValidationResult(
            status=ValidationStatus.PASS,
            findings=tuple(f for r in results for f in r.findings),
            rule_bundle_version="+".join(sorted({r.rule_bundle_version for r in results})),
            validator_id="+".join(sorted({r.validator_id for r in results})),
        )
        return contexts, merged

    async def _plan_denied(self, run: RunRecord, decision: PolicyDecision) -> RunRecord:
        payload = {"status": "FAIL", "findings": [], "policy_reasons": list(decision.reasons)}
        run = await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [(RunEventType.VALIDATION_COMPLETED, payload, None)],
        )
        return await self._set_run_state(
            run, RunState.FAILED, "policy denied", code=ReasonCode.POLICY_DENIED
        )

    async def _propose_plan(
        self,
        run: RunRecord,
        cont: _Continuation,
        plan: ActionPlan,
        canonical: dict[str, Any],
        digest: str,
        validation: ValidationResult,
    ) -> RunRecord:
        """Store the plan and its first step's action, and wait for the one approval."""
        inputs = tuple(step["input"] for step in canonical["steps"])
        action = self._plan_action(
            cont, plan, 0, dict(plan.steps[0].proposal.arguments), inputs[0], digest
        )
        compiled = {
            "plan_id": plan.plan_id,
            "plan_digest": digest,
            "step_count": len(plan.steps),
            "task_id": plan.task_id,
            "task_version": plan.task_version,
        }
        await self._store.put_plan(
            cont.ctx.tenant_id, run.run_id, plan, [(RunEventType.IR_PLAN_COMPILED, compiled, None)]
        )
        cont.plan = _PlanState(
            plan_id=plan.plan_id,
            step_ids=tuple(step.step_id for step in plan.steps),
            inputs=inputs,
            action_ids=[action.action_id],
        )
        await self._store.put_action(action, None, [self._proposal_event(action)])
        cont.last_action_id = action.action_id
        evidence = [cont.observations[r].evidence for r in sorted(cont.observations)]
        findings = [f.model_dump(mode="json") for f in validation.findings]
        action = await self._transition_with_steps(
            action,
            ActionState.VALIDATED,
            (
                RunEventType.VALIDATION_COMPLETED,
                {"status": validation.status, "findings": findings},
            ),
            await self._step_pair(
                action, StepKind.VALIDATE, StepStatus.SUCCEEDED, input_refs=evidence
            ),
        )
        wait = await self._step_start(action, StepKind.APPROVAL_WAIT)
        return await self._await_approval(run, cont, action, canonical, validation, [*wait])

    def _plan_action(
        self,
        cont: _Continuation,
        plan: ActionPlan,
        index: int,
        arguments: dict[str, Any],
        approved: dict[str, Any],
        digest: str,
    ) -> ActionRecord:
        """A plan step's action, bound to what the approval bound for it: its operation id,
        binding, connection and credential versions come from its approved digest input."""
        ctx = cont.ctx
        return ActionRecord(
            action_id=new_id("act"),
            tenant_id=ctx.tenant_id,
            run_id=ctx.run_id,
            logical_operation_id=str(approved["logical_operation_id"]),
            contract_id=plan.steps[index].proposal.contract_id,
            binding_id=str(approved["binding_id"]),
            connection_id=str(approved["connection_id"]),
            connection_version=int(approved["connection_version"]),
            credential_subject=str(approved["credential_subject"]),
            credential_version=str(approved["credential_version"]),
            approved_facts=tuple(
                ApprovedFact(contract_id=o.contract_id, data=dict(o.data), evidence=o.evidence)
                for o in cont.observations.values()
            ),
            arguments=arguments,
            digest=digest,
            state=ActionState.PROPOSED,
            revision=1,
            supersedes_action_id=cont.last_action_id if index == 0 else None,
            plan_id=plan.plan_id,
            step_index=index,
        )

    @staticmethod
    def _proposal_event(action: ActionRecord) -> tuple[RunEventType, dict[str, Any], str]:
        payload = {
            "contract_id": action.contract_id,
            "arguments": action.arguments,
            "supersedes": action.supersedes_action_id,
        }
        return (RunEventType.PROPOSAL_CREATED, payload, action.action_id)

    # -- dispatch --------------------------------------------------------------------------
    async def _run_plan(
        self, cont: _Continuation, action: ActionRecord, approval: ApprovalRecord
    ) -> RunRecord:
        """Dispatch an approved plan, step after verified step, inside this call."""
        self._plan_runs.add(cont.ctx.run_id)
        try:
            return await self._dispatch(cont, action, approval)
        finally:
            self._plan_runs.discard(cont.ctx.run_id)

    async def _after_step_verified(self, cont: _Continuation, action: ActionRecord) -> RunRecord:
        """A step verified and steps remain: ``VERIFYING -> RUNNING`` and the next step, or,
        outside `_run_plan` (recovery, reconciliation), stop: recovery never sends a write."""
        run = await self._store.get_run(cont.ctx.tenant_id, cont.ctx.run_id)
        plan = cont.plan
        if plan is None or cont.ctx.run_id not in self._plan_runs:
            return await self._set_run_state(
                run, RunState.FAILED, PLAN_INTERRUPTED, code=ReasonCode.INTERRUPTED
            )
        run = await self._set_run_state(run, RunState.RUNNING)
        return await self._start_step(cont, plan.current + 1)

    async def _start_step(self, cont: _Continuation, index: int) -> RunRecord:
        """Resolve step ``index``'s lineage from the verified outcomes, record it, create its
        action with the resolved arguments, then revalidate and dispatch it (`_dispatch`)."""
        ctx = cont.ctx
        state = cont.plan
        assert state is not None
        plan = await self._store.get_plan(ctx.tenant_id, state.plan_id)
        step = plan.steps[index]
        state.current = index
        descriptor = self._registry.descriptor(step.proposal.contract_id)
        schema = self._registry.input_schemas.get(descriptor.input_schema_id)
        try:
            arguments, resolved = resolve_lineage(step, state.verified, schema)
        except LineageRejected as exc:
            return await self._lineage_rejected(cont, exc)
        approval = await self._plan_approval(cont)
        action = self._plan_action(
            cont, plan, index, arguments, state.inputs[index], approval.action_digest
        )
        state.action_ids.append(action.action_id)
        events: list[Any] = [self._proposal_event(action)]
        if resolved:
            lineage = {
                "plan_id": plan.plan_id,
                "step_id": step.step_id,
                "step_index": index,
                "values": resolved,
            }
            events.append((RunEventType.IR_LINEAGE_RESOLVED, lineage, action.action_id))
        events.extend(await self._step_start(action, StepKind.VALIDATE))
        await self._store.put_action(action, None, events)
        cont.last_action_id = cont.pending_action_id = action.action_id
        return await self._dispatch(cont, action, approval)

    async def _lineage_rejected(self, cont: _Continuation, exc: LineageRejected) -> RunRecord:
        """A placeholder without a verified value of its declared type stops the plan before
        the step reserves. The code is VALIDATION_FAILED until Task 2c.8 adds
        ``PLAN_LINEAGE_REJECTED``; the finding is fixed (no model or provider text)."""
        finding = _fixed("KERNEL-PLAN-LINEAGE", LINEAGE_MESSAGES[exc.kind])
        run = await self._store.get_run(cont.ctx.tenant_id, cont.ctx.run_id)
        run = await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [
                (
                    RunEventType.VALIDATION_COMPLETED,
                    {"status": "FAIL", "findings": [finding.model_dump(mode="json")]},
                    None,
                )
            ],
        )
        cont.pending_action_id = None
        return await self._set_run_state(
            run, RunState.FAILED, "lineage rejected", code=ReasonCode.VALIDATION_FAILED
        )

    async def _plan_approval(self, cont: _Continuation) -> ApprovalRecord:
        """The plan's one approval, recorded on its first step's action."""
        state = cont.plan
        assert state is not None
        for approval in await self._store.list_approvals(cont.ctx.tenant_id, state.action_ids[0]):
            if approval.approval_id == state.approval_id:
                return approval
        raise KernelError(ErrorCode.CONFLICT, "the plan's approval is unavailable")
