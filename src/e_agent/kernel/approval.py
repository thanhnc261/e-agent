"""Approval digest input and the server-built ApprovalPresentation (ADR 0006, UI §4.2)."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.capability import CapabilityDescriptor, Reversibility, Risk
from e_agent.contracts.common import Record, UtcDatetime
from e_agent.contracts.digest import digest
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.plan import ActionPlan, LineageRef
from e_agent.contracts.validation import Finding


def digest_input(
    *,
    tenant_id: str,
    requester_id: str,
    logical_operation_id: str,
    contract_id: str,
    binding_id: str,
    connection_id: str,
    connection_version: int,
    credential_subject: str,
    arguments: dict[str, Any],
    expected_effects: Iterable[str],
    evidence: Iterable[EvidenceRef],
    rule_bundle_version: str,
    policy_version: str,
    fact_digests: Mapping[str, str] | None = None,
    credential_version: str = "none",
) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "requester_id": requester_id,
        "logical_operation_id": logical_operation_id,
        "contract_id": contract_id,
        "binding_id": binding_id,
        "connection_id": connection_id,
        "connection_version": str(connection_version),
        "credential_subject": credential_subject,
        "credential_version": credential_version,
        "arguments": arguments,
        "expected_effects": list(expected_effects),
        "evidence": [
            {
                "id": e.evidence_id,
                "source": e.source,
                "revision": e.revision or "",
                "completeness": str(e.completeness),
                "fact_digest": (fact_digests or {}).get(e.evidence_id, ""),
            }
            for e in sorted(evidence, key=lambda e: e.evidence_id)
        ],
        "rule_bundle_version": rule_bundle_version,
        "policy_version": policy_version,
    }


def fact_digest(data: Mapping[str, Any]) -> str:
    """Fingerprint authorized facts, excluding observation metadata and timestamps."""
    encoded = json.dumps(
        dict(data), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return "facts-json-v1:" + hashlib.sha256(encoded).hexdigest()


def compute_digest(canonical_proposal: dict[str, Any]) -> str:
    return digest(canonical_proposal)


PLAN_SCHEMA = "plan.v1"
"""The plan digest wrapper's schema tag (target §6.4.4)."""


def plan_digest_wrapper(
    steps: Iterable[tuple[str, Iterable[str], dict[str, Any]]],
) -> dict[str, Any]:
    """The digest input of a plan with two or more steps (target §6.4.4, ADR 0025).

    ``steps`` are ``(step_id, depends_on, step digest input)`` in step-index order; each step
    input is a `digest_input` with placeholders in its arguments. A 1-step plan never uses
    this wrapper: its approval digest is that step's action digest (`kernel/ir.py`)."""
    return {
        "plan_schema": PLAN_SCHEMA,
        "steps": [
            {"step_id": step_id, "depends_on": sorted(depends_on), "input": step_input}
            for step_id, depends_on, step_input in steps
        ],
    }


class MaterialField(Record):
    path: str
    value: str
    previous_value: str | None = None  # baseline selected by comparison (current/proposal)
    changed: bool = False
    label: str | None = None
    proposal_previous_value: str | None = None
    comparison: str | None = None


class PlanStepPresentation(Record):
    """One step of a multi-step plan on the approval card (ADR 0024). Its arguments show a
    lineage placeholder as ``from step N: <pointer>``; ``risk`` and ``reversibility`` are the
    capability's declarations (ADR 0029), a presentation annotation outside the digest."""

    step_id: str
    step_index: int
    contract_id: str
    binding_id: str
    connection_id: str
    depends_on: tuple[str, ...] = ()
    risk: Risk
    reversibility: Reversibility
    material_fields: tuple[MaterialField, ...]
    expected_effects: tuple[str, ...] = ()


class ApprovalPresentation(Record):
    """Everything any UI needs to show an approval; the digest input is included verbatim.

    For a plan of two or more steps (ADR 0024) the digest is the plan digest, the top-level
    action fields are the first step's, and ``plan_steps`` lists every step with the plan's
    ``highest_risk`` and its ``irreversible_steps`` (ADR 0029). A single action, a 1-step
    plan included, leaves the three empty, exactly as before Task 2c.7."""

    run_id: str
    action_id: str
    run_revision: int
    digest: str
    expires_at: UtcDatetime
    contract_id: str
    binding_id: str
    connection_id: str
    credential_subject: str
    canonical_proposal: dict[str, Any]
    material_fields: tuple[MaterialField, ...]
    findings: tuple[Finding, ...]
    display_title: str | None = None
    expected_effects: tuple[str, ...] = ()
    plan_steps: tuple[PlanStepPresentation, ...] = ()
    highest_risk: Risk | None = None
    irreversible_steps: tuple[str, ...] = ()


def _flatten(arguments: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key in sorted(arguments):
        value = arguments[key]
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{path}."))
        else:
            flat[path] = "null" if value is None else str(value)
    return flat


def material_fields(
    arguments: dict[str, Any], previous: dict[str, Any] | None = None
) -> tuple[MaterialField, ...]:
    """Flatten the proposal; mark what changed against the superseded proposal, if any."""
    current = _flatten(arguments)
    if previous is None:
        return tuple(MaterialField(path=p, value=v) for p, v in current.items())
    before = _flatten(previous)
    return tuple(
        MaterialField(path=p, value=v, previous_value=before.get(p), changed=before.get(p) != v)
        for p, v in current.items()
    )


def presentation_for(
    action: ActionRecord,
    *,
    run_revision: int,
    canonical_proposal: dict[str, Any],
    findings: Iterable[Finding],
    expires_at: Any,
    previous_arguments: dict[str, Any] | None = None,
    input_schema: Mapping[str, Any] | None = None,
) -> ApprovalPresentation:
    schema = input_schema or {}
    fields = material_fields(action.arguments, previous_arguments)
    metadata = schema.get("x-presentation", {})
    baseline_field = metadata.get("baseline_reference") if isinstance(metadata, dict) else None
    baseline = None
    if baseline_field and baseline_field in action.arguments:
        candidates = [
            f.data
            for f in action.approved_facts
            if f.data.get(baseline_field) == action.arguments[baseline_field]
        ]
        if len(candidates) == 1:
            baseline = candidates[0]
    properties = schema.get("properties", {})
    labeled = []
    for field in fields:
        prop = properties.get(field.path, {})
        prior = None if baseline is None else _flatten(baseline).get(field.path)
        labeled.append(
            field.model_copy(
                update={
                    "label": prop.get("title"),
                    "proposal_previous_value": field.previous_value,
                    "previous_value": prior if baseline_field else field.previous_value,
                    "changed": (prior is not None and prior != field.value)
                    if baseline_field
                    else field.changed,
                    "comparison": "current"
                    if baseline_field
                    else "proposal"
                    if previous_arguments
                    else None,
                }
            )
        )
    order = {path: index for index, path in enumerate(properties)}
    labeled.sort(key=lambda field: (order.get(field.path, len(order)), field.path))
    title = schema.get("title")
    if isinstance(title, str):
        title = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", title)
    return ApprovalPresentation(
        run_id=action.run_id,
        action_id=action.action_id,
        run_revision=run_revision,
        digest=action.digest,
        expires_at=expires_at,
        contract_id=action.contract_id,
        binding_id=action.binding_id,
        connection_id=action.connection_id,
        credential_subject=action.credential_subject,
        canonical_proposal=canonical_proposal,
        material_fields=tuple(labeled),
        display_title=title if isinstance(title, str) else None,
        expected_effects=tuple(canonical_proposal.get("expected_effects", ())),
        findings=tuple(findings),
    )


RISK_ORDER = (Risk.READ, Risk.WRITE_LOW, Risk.WRITE_HIGH, Risk.DESTRUCTIVE)


def _shown(value: Any, index: Mapping[str, int]) -> Any:
    """Arguments for the card: a placeholder becomes ``from step N: <pointer>`` (1-based)."""
    if isinstance(value, LineageRef):
        return f"from step {index[value.step_id] + 1}: {value.path}"
    if isinstance(value, Mapping):
        return {k: _shown(v, index) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_shown(v, index) for v in value]
    return value


def plan_presentation(
    plan: ActionPlan,
    inputs: Iterable[Mapping[str, Any]],
    descriptors: Mapping[str, CapabilityDescriptor],
) -> dict[str, Any]:
    """The plan fields of an `ApprovalPresentation`: every step, the highest declared risk
    and the irreversible steps. ``inputs`` are the steps' approved digest inputs (their
    binding), in step-index order. Pure."""
    index = {step.step_id: position for position, step in enumerate(plan.steps)}
    steps = []
    for position, (step, approved) in enumerate(zip(plan.steps, inputs, strict=True)):
        descriptor = descriptors[step.proposal.contract_id]
        steps.append(
            PlanStepPresentation(
                step_id=step.step_id,
                step_index=position,
                contract_id=step.proposal.contract_id,
                binding_id=str(approved["binding_id"]),
                connection_id=step.proposal.connection_id,
                depends_on=step.depends_on,
                risk=descriptor.risk,
                reversibility=descriptor.reversibility,
                material_fields=material_fields(_shown(dict(step.proposal.arguments), index)),
                expected_effects=step.proposal.expected_effects,
            )
        )
    return {
        "plan_steps": tuple(steps),
        "highest_risk": max((s.risk for s in steps), key=RISK_ORDER.index),
        "irreversible_steps": tuple(
            s.step_id for s in steps if s.reversibility is Reversibility.IRREVERSIBLE
        ),
    }
