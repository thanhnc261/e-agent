"""Approval digest input and the server-built ApprovalPresentation (ADR 0006, UI §4.2)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.common import Record, UtcDatetime
from e_agent.contracts.digest import digest
from e_agent.contracts.evidence import EvidenceRef
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
        "arguments": arguments,
        "expected_effects": list(expected_effects),
        "evidence": [
            {"id": e.evidence_id, "source": e.source, "revision": e.revision or ""}
            for e in sorted(evidence, key=lambda e: e.evidence_id)
        ],
        "rule_bundle_version": rule_bundle_version,
        "policy_version": policy_version,
    }


def compute_digest(canonical_proposal: dict[str, Any]) -> str:
    return digest(canonical_proposal)


class MaterialField(Record):
    path: str
    value: str
    previous_value: str | None = None  # value in the superseded (blocked) proposal
    changed: bool = False


class ApprovalPresentation(Record):
    """Everything any UI needs to show an approval; the digest input is included verbatim."""

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
) -> ApprovalPresentation:
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
        material_fields=material_fields(action.arguments, previous_arguments),
        findings=tuple(findings),
    )
