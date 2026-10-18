"""The execution IR's pure functions (ADR 0025, target §6.4.3-§6.4.5).

`compile_proposal` turns one proposal into a 1-step plan, `validate_plan` checks a plan's
policy against its task definition, and `plan_digest_input` builds the input of the plan's
approval digest. None of them touches a store, a driver, a registry or the network: the
caller passes what the kernel already resolved. Nothing calls them at run time until the
shadow path (Task 2c.5) and the `on` path (Task 2c.6).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from e_agent.contracts.capability import EffectKind
from e_agent.contracts.common import Record
from e_agent.contracts.digest import CanonicalizationError, canonicalize
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.plan import (
    ActionPlan,
    ActionProposal,
    LineageRef,
    PlannedStep,
    lineage_refs,
    plan_from_wire,
    plan_to_wire,
)
from e_agent.contracts.task import TaskDefinition
from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.kernel.approval import compute_digest, digest_input, plan_digest_wrapper
from pydantic import Field

SINGLE_STEP_ID = "step-1"
"""The step id of a compiled single proposal; a 1-step plan's step id is not in its digest."""


# -- compile -----------------------------------------------------------------------------
def compile_proposal(proposal: ActionProposal, task: TaskDefinition, *, plan_id: str) -> ActionPlan:
    """One `ProposeAction` as a 1-step plan for ``task`` (target §6.4.3).

    The task id and version come from the definition and the step id is `SINGLE_STEP_ID`.
    The caller assigns ``plan_id``: the stores refuse a second plan with the same id in a
    tenant, and one run may compile several proposals (repairs), so the id cannot be derived
    from the definition alone. The result depends only on the arguments."""
    return ActionPlan(
        plan_id=plan_id,
        task_id=task.task_id,
        task_version=task.version,
        steps=(PlannedStep(step_id=SINGLE_STEP_ID, proposal=proposal),),
    )


# -- validate ----------------------------------------------------------------------------
class PlanValidationContext(Record):
    """What the kernel resolved before validating a plan; plain data, no services."""

    effects: dict[str, EffectKind]
    """Each known capability's effect, from its admitted descriptor."""
    max_admitted_writes: int = Field(ge=0)
    """The run's effective budget: the profile's, narrowed by the task definition."""


def _finding(rule_id: str, message: str) -> Finding:
    return Finding(rule_id=rule_id, rule_version="1", status=ValidationStatus.FAIL, message=message)


def validate_plan(
    plan: ActionPlan, task: TaskDefinition, ctx: PlanValidationContext
) -> tuple[Finding, ...]:
    """The kernel's pure check of a plan (target §6.4.3). An empty tuple means the plan
    passes its structure rules, the task policy and the digest profile; per-step domain
    validation and policy are the caller's, through its existing validators (Task 2c.6).

    Finding codes: ``KERNEL-PLAN-STRUCTURE`` (the plan's own rules fail when re-applied),
    ``KERNEL-PLAN-TASK`` (the plan names another definition or version),
    ``KERNEL-PLAN-CAPABILITY`` (a step's capability is outside the definition),
    ``KERNEL-PLAN-UNKNOWN-CAPABILITY`` (no resolved effect for it),
    ``KERNEL-PLAN-READ-STEP`` (a plan step proposes a read) and ``KERNEL-PLAN-WRITES``
    (more write steps than ``max_admitted_writes``), and ``KERNEL-ARGS`` (a step's arguments,
    placeholders in wire form, are outside the digest profile; the code and detail of
    `kernel/proposals.py`). Never raises for a bad plan."""
    try:
        # Re-apply the plan rules to a built plan through the wire form: a placeholder's
        # dump is refused as a literal by `model_validate`, and a plain revalidation of a
        # dump would refuse every plan that holds one (ADR 0025, 2c.3 review R-2).
        plan_from_wire(plan_to_wire(plan))
    except ValueError as exc:
        return (_finding("KERNEL-PLAN-STRUCTURE", f"plan structure is invalid: {exc}"),)
    findings: list[Finding] = []
    if (plan.task_id, plan.task_version) != (task.task_id, task.version):
        findings.append(
            _finding(
                "KERNEL-PLAN-TASK",
                f"plan is for {plan.task_id}@{plan.task_version}, "
                f"not {task.task_id}@{task.version}",
            )
        )
    allowed = set(task.capabilities)
    writes = 0
    for step in plan.steps:
        profile = _profile_finding(step)
        if profile is not None:
            findings.append(profile)
        contract_id = step.proposal.contract_id
        if contract_id not in allowed:
            findings.append(
                _finding(
                    "KERNEL-PLAN-CAPABILITY",
                    f"step {step.step_id!r}: {contract_id} is not in task definition "
                    f"{task.task_id}@{task.version}",
                )
            )
            continue
        effect = ctx.effects.get(contract_id)
        if effect is None:
            findings.append(
                _finding(
                    "KERNEL-PLAN-UNKNOWN-CAPABILITY",
                    f"step {step.step_id!r}: no admitted capability {contract_id}",
                )
            )
        elif effect is EffectKind.READ:
            findings.append(
                _finding(
                    "KERNEL-PLAN-READ-STEP",
                    f"step {step.step_id!r}: {contract_id} is a read; reads are not plan steps",
                )
            )
        elif effect is EffectKind.WRITE:
            writes += 1
    if writes > ctx.max_admitted_writes:
        findings.append(
            _finding(
                "KERNEL-PLAN-WRITES",
                f"plan has {writes} write steps; the run admits {ctx.max_admitted_writes}",
            )
        )
    return tuple(findings)


# -- digest ------------------------------------------------------------------------------
def _digest_arguments(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """A step's arguments for its digest input: the Python values, with only each
    placeholder replaced by its wire mapping ``{"$lineage": {"step", "path"}}``.

    Every other value passes through unchanged, so `canonicalize` refuses exactly what it
    refuses on the 1-step path (a set, a number, an int key, bytes). Never a `model_dump`:
    a JSON-mode dump lists a set in hash order and coerces Decimal, NaN, int keys and bytes
    to strings or null (2c.4 review R-1). A literal `$lineage` key anywhere, or a
    placeholder with a bad pointer, raises `ValueError` (`lineage_refs`)."""
    for _ in lineage_refs(arguments):
        pass
    return {key: _encode_placeholders(value) for key, value in arguments.items()}


def _encode_placeholders(value: Any) -> Any:
    if isinstance(value, LineageRef):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {key: _encode_placeholders(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_encode_placeholders(item) for item in value]
    return value


def _profile_finding(step: PlannedStep) -> Finding | None:
    """``KERNEL-ARGS`` when the step's digest arguments are outside the digest profile."""
    try:
        canonicalize(_digest_arguments(step.proposal.arguments))
    except CanonicalizationError as exc:
        return _finding(
            "KERNEL-ARGS",
            f"step {step.step_id!r}: arguments outside the digest profile: {exc}",
        )
    return None


class StepDigestContext(Record):
    """What the kernel resolved for one step's digest input (`digest_input`, ADR 0006).

    A step after the first binds the evidence and fact digests known when the plan was
    proposed, which may be none (target §6.4.4).

    ``evidence`` carries every observation of the run's continuation, as `kernel/proposals.py`
    builds it today (sorted by evidence id there and in `digest_input`), not only the
    proposal's ``evidence_ids``; otherwise a 1-step plan's digest would not equal the action
    digest."""

    tenant_id: str
    requester_id: str
    binding_id: str
    connection_version: int
    credential_subject: str
    credential_version: str = "none"
    evidence: tuple[EvidenceRef, ...] = ()
    fact_digests: dict[str, str] = Field(default_factory=dict)
    rule_bundle_version: str
    policy_version: str


def step_operation_id(plan_id: str, step_id: str) -> str:
    """The logical operation id of a step in a plan of two or more steps (target §6.4.5).

    ``op_`` and 32 hex digits of SHA-256 over the canonical ``{"plan_id", "step_id"}``
    object: the same shape as a host-assigned ``new_id("op")``, deterministic, and free of
    separator ambiguity. A 1-step plan keeps the run's logical operation id instead."""
    canonical = canonicalize({"plan_id": plan_id, "step_id": step_id}).encode("utf-8")
    return "op_" + hashlib.sha256(canonical).hexdigest()[:32]


def _step_input(
    step: PlannedStep,
    ctx: StepDigestContext,
    *,
    logical_operation_id: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    proposal = step.proposal
    return digest_input(
        tenant_id=ctx.tenant_id,
        requester_id=ctx.requester_id,
        logical_operation_id=logical_operation_id,
        contract_id=proposal.contract_id,
        binding_id=ctx.binding_id,
        connection_id=proposal.connection_id,
        connection_version=ctx.connection_version,
        credential_subject=ctx.credential_subject,
        arguments=arguments,
        expected_effects=proposal.expected_effects,
        evidence=ctx.evidence,
        rule_bundle_version=ctx.rule_bundle_version,
        policy_version=ctx.policy_version,
        fact_digests=ctx.fact_digests,
        credential_version=ctx.credential_version,
    )


def plan_digest_input(
    plan: ActionPlan,
    contexts: Mapping[str, StepDigestContext],
    *,
    run_operation_id: str,
) -> dict[str, Any]:
    """The input of a plan's approval digest (target §6.4.4); ``contexts`` maps step ids.

    A 1-step plan's input is that step's action digest input, byte for byte today's
    (`kernel/proposals.py`): the run's logical operation id and the proposal's arguments as
    they are, without the wire form (a 1-step plan cannot hold a placeholder). A plan of two
    or more steps is wrapped (`plan_digest_wrapper`); each step's arguments are its Python
    values with each placeholder as ``{"$lineage": {"step", "path"}}`` (`_digest_arguments`),
    and its logical operation id comes from `step_operation_id`. Run `validate_plan` first:
    this function re-checks placeholders and literal `$lineage` keys, not the plan rules."""
    missing = [s.step_id for s in plan.steps if s.step_id not in contexts]
    if missing:
        raise ValueError(f"no digest context for steps {missing!r}")
    if len(plan.steps) == 1:
        (step,) = plan.steps
        return _step_input(
            step,
            contexts[step.step_id],
            logical_operation_id=run_operation_id,
            arguments=dict(step.proposal.arguments),
        )
    return plan_digest_wrapper(
        (
            step.step_id,
            step.depends_on,
            _step_input(
                step,
                contexts[step.step_id],
                logical_operation_id=step_operation_id(plan.plan_id, step.step_id),
                arguments=_digest_arguments(step.proposal.arguments),
            ),
        )
        for step in plan.steps
    )


def plan_digest(
    plan: ActionPlan,
    contexts: Mapping[str, StepDigestContext],
    *,
    run_operation_id: str,
) -> str:
    """The plan's approval digest: `compute_digest` over `plan_digest_input`."""
    return compute_digest(plan_digest_input(plan, contexts, run_operation_id=run_operation_id))
