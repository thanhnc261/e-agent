"""The execution IR's pure functions (ADR 0025, target §6.4.3-§6.4.5).

`compile_proposal` turns one proposal into a 1-step plan, `validate_plan` checks a plan's
policy against its task definition, and `plan_digest_input` builds the input of the plan's
approval digest. None of them touches a store, a driver, a registry or the network: the
caller passes what the kernel already resolved. Nothing calls them at run time until the
shadow path (Task 2c.5) and the `on` path (Task 2c.6).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from typing import Any

from e_agent.contracts.capability import EffectKind
from e_agent.contracts.common import Record
from e_agent.contracts.digest import CanonicalizationError, canonicalize
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.plan import (
    LINEAGE_KEY,
    ActionPlan,
    ActionProposal,
    LineageRef,
    PlannedStep,
    check_plan_rules,
    encode_arguments,
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
    except CanonicalizationError:
        # `plan_to_wire` re-applied the plan rules, then refused a step's arguments: each
        # such step is reported below as ``KERNEL-ARGS`` (Codex review C-1).
        pass
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
def _profile_finding(step: PlannedStep) -> Finding | None:
    """``KERNEL-ARGS`` when the step's digest arguments are outside the digest profile."""
    try:
        encode_arguments(step.proposal.arguments)
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
    values with each placeholder as ``{"$lineage": {"step", "path"}}`` (`encode_arguments`),
    and its logical operation id comes from `step_operation_id`. Run `validate_plan` first:
    this function re-applies the plan rules (`check_plan_rules`) but not task policy."""
    check_plan_rules(plan)
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
                arguments=encode_arguments(step.proposal.arguments),
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


# -- lineage (target §6.4.3, §6.4.5) -----------------------------------------------------
_JSON_TYPES: dict[str, Callable[[Any], bool]] = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
    "object": lambda v: isinstance(v, Mapping),
    "array": lambda v: isinstance(v, list),
}

LINEAGE_MESSAGES = {
    "missing": "A lineage placeholder names a value the earlier step's verified outcome "
    "does not hold.",
    "type": "A lineage value does not have the type its input schema declares.",
}
"""The fixed messages of the run-time ``KERNEL-PLAN-LINEAGE`` finding (no model text)."""


class LineageRejected(ValueError):
    """A placeholder cannot be resolved: ``kind`` is a key of `LINEAGE_MESSAGES`."""

    def __init__(self, kind: str) -> None:
        super().__init__(LINEAGE_MESSAGES[kind])
        self.kind = kind


def step_matches_input(step: PlannedStep, approved: Mapping[str, Any]) -> bool:
    """Whether a stored plan step is still the step its approved digest input bound: the
    same contract, connection and expected effects, and the same wire-form arguments
    (`encode_arguments`, before lineage resolution), compared canonically (2c.7 R-3)."""
    proposal = step.proposal
    try:
        rebuilt = {
            "contract_id": proposal.contract_id,
            "connection_id": proposal.connection_id,
            "expected_effects": list(proposal.expected_effects),
            "arguments": encode_arguments(proposal.arguments),
        }
        bound = {key: approved.get(key) for key in rebuilt}
        return canonicalize(rebuilt) == canonicalize(bound)
    except ValueError:  # outside the digest profile: it cannot be the approved step
        return False


def has_placeholders(proposal: ActionProposal) -> bool:
    return any(True for _ in lineage_refs(proposal.arguments))


def _pointer(segments: tuple[str, ...]) -> str:
    return "".join("/" + s.replace("~", "~0").replace("/", "~1") for s in segments)


def _deref(node: Any, root: Mapping[str, Any]) -> Any:
    """Follow a local ``#/$defs/...`` reference, as pydantic writes them."""
    ref = node.get("$ref") if isinstance(node, Mapping) else None
    if isinstance(ref, str) and ref.startswith("#/"):
        target: Any = root
        for part in ref[2:].split("/"):
            target = target.get(part) if isinstance(target, Mapping) else None
        return target if isinstance(target, Mapping) else {}
    return node if isinstance(node, Mapping) else {}


def _nodes_at(node: Any, segments: tuple[str, ...], root: Mapping[str, Any]) -> list[Any]:
    node = _deref(node, root)
    branches = node.get("anyOf") or node.get("oneOf")
    if isinstance(branches, list):
        return [n for b in branches for n in _nodes_at(b, segments, root)]
    if not segments:
        return [node]
    head, rest = segments[0], segments[1:]
    properties = node.get("properties")
    if isinstance(properties, Mapping) and head in properties:
        return _nodes_at(properties[head], rest, root)
    if "items" in node and head.isdigit():
        return _nodes_at(node["items"], rest, root)
    return []


def declared_types(schema: Mapping[str, Any] | None, segments: tuple[str, ...]) -> set[str]:
    """The JSON types the input schema declares at an argument location; empty when the
    schema declares none there (an undeclared argument cannot be type-checked)."""
    if not schema:
        return set()
    types: set[str] = set()
    for node in _nodes_at(schema, segments, schema):
        declared = node.get("type")
        for name in [declared] if isinstance(declared, str) else declared or []:
            if name in _JSON_TYPES:
                types.add(name)
    return types


def _placeholders(
    value: Any, location: tuple[str, ...]
) -> list[tuple[tuple[str, ...], LineageRef]]:
    if isinstance(value, LineageRef):
        return [(location, value)]
    if isinstance(value, Mapping):
        return [p for k, v in value.items() for p in _placeholders(v, (*location, str(k)))]
    if isinstance(value, list | tuple):
        return [p for i, v in enumerate(value) for p in _placeholders(v, (*location, str(i)))]
    return []


def lineage_type_findings(
    step: PlannedStep, schema: Mapping[str, Any] | None
) -> tuple[Finding, ...]:
    """``KERNEL-PLAN-LINEAGE`` for each placeholder whose argument has no declared type in
    the consuming step's input schema (target §6.4.3: a placeholder is treated as a value of
    the type its input schema declares). Pure; checked before approval."""
    return tuple(
        _finding(
            "KERNEL-PLAN-LINEAGE",
            f"step {step.step_id!r}: argument {_pointer(location)} has no type in its "
            "input schema, so its lineage value cannot be type-checked",
        )
        for location, _ in _placeholders(step.proposal.arguments, ())
        if not declared_types(schema, location)
    )


def _pointer_get(document: Any, path: str) -> Any:
    """The value at an RFC 6901 pointer; `LineageRejected` ("missing") when there is none."""
    for raw in path.split("/")[1:] if path else ():
        segment = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(document, Mapping) and segment in document:
            document = document[segment]
        elif (
            isinstance(document, list)
            and segment.isdigit()
            and (segment == "0" or not segment.startswith("0"))
            and int(segment) < len(document)
        ):
            document = document[int(segment)]
        else:
            raise LineageRejected("missing")
    return document


def _clone(value: Any) -> Any:
    """A copy of a JSON-mode value, so a resolved argument never aliases a verified one."""
    if isinstance(value, Mapping):
        return {k: _clone(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clone(v) for v in value]
    return value


def substitute_lineage(value: Any, verified: Mapping[str, Mapping[str, Any]]) -> Any:
    """Wire-form arguments (`encode_arguments`) with each ``{"$lineage": {"step", "path"}}``
    replaced by a copy of the value at its pointer in that step's verified values: what an
    approved step input binds once its lineage is resolved (Codex C-3). Pure; raises
    `LineageRejected` or ``KeyError`` when a value is missing."""
    if isinstance(value, Mapping):
        body = value.get(LINEAGE_KEY)
        if set(value) == {LINEAGE_KEY} and isinstance(body, Mapping):
            return _clone(_pointer_get(verified[str(body["step"])], str(body["path"])))
        return {k: substitute_lineage(v, verified) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [substitute_lineage(v, verified) for v in value]
    return value


def resolve_lineage(
    step: PlannedStep,
    verified: Mapping[str, Mapping[str, Any]],
    schema: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The step's arguments with each placeholder replaced by the value at its pointer in the
    named earlier step's verified values (ADR 0025's one rule), and the record of each
    resolution. ``verified`` maps a step id to its verifier's read-back values, never a
    receipt or model output. Raises `LineageRejected` for a missing value ("missing") or a
    value whose JSON type the schema does not declare there ("type"). Pure."""
    resolved: list[dict[str, Any]] = []

    def walk(value: Any, location: tuple[str, ...]) -> Any:
        if not _placeholders(value, location):
            return value
        if isinstance(value, LineageRef):
            source = verified.get(value.step_id)
            if source is None:
                raise LineageRejected("missing")
            got = _clone(_pointer_get(source, value.path))
            types = declared_types(schema, location)
            if not any(_JSON_TYPES[name](got) for name in types):
                raise LineageRejected("type")
            resolved.append(
                {
                    "argument": _pointer(location),
                    "from_step": value.step_id,
                    "path": value.path,
                    "value": got,
                }
            )
            return got
        if isinstance(value, Mapping):
            return {k: walk(v, (*location, str(k))) for k, v in value.items()}
        return [walk(v, (*location, str(i))) for i, v in enumerate(value)]

    arguments = {key: walk(value, (key,)) for key, value in step.proposal.arguments.items()}
    return arguments, resolved
