"""Host-owned presentation metadata never changes approval terms or invents baselines."""

from datetime import UTC, datetime

from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.evidence import ApprovedFact, EvidenceRef
from e_agent.kernel.approval import presentation_for

NOW = datetime(2026, 10, 8, tzinfo=UTC)


def action(facts: tuple[ApprovedFact, ...] = ()) -> ActionRecord:
    return ActionRecord(
        action_id="action",
        tenant_id="tenant",
        run_id="run",
        logical_operation_id="op",
        contract_id="example.amend.v1",
        binding_id="binding",
        connection_id="connection",
        connection_version=1,
        credential_subject="connection@1/service",
        arguments={"record_ref": "record:1", "quantity": "9"},
        digest="unchanged",
        state=ActionState.AWAITING_APPROVAL,
        revision=1,
        approved_facts=facts,
    )


def fact(quantity: str = "5", ref: str = "record:1") -> ApprovedFact:
    return ApprovedFact(
        contract_id="example.read.v1",
        data={"record_ref": ref, "quantity": quantity},
        evidence=EvidenceRef(
            evidence_id="e",
            tenant_id="tenant",
            source="fixture",
            locator=ref,
            revision="1",
            observed_at=NOW,
            scope="tenant",
        ),
    )


def present(facts: tuple[ApprovedFact, ...] = ()):
    a = action(facts)
    return presentation_for(
        a,
        run_revision=3,
        canonical_proposal={"arguments": a.arguments},
        findings=(),
        expires_at=NOW,
        previous_arguments={"record_ref": "record:1", "quantity": "7"},
        input_schema={
            "title": "AmendRecord",
            "properties": {"quantity": {"title": "Quantity"}},
            "x-presentation": {"baseline_reference": "record_ref"},
        },
    )


def test_actual_baseline_and_superseded_proposal_are_distinct() -> None:
    p = present((fact(),))
    qty = next(f for f in p.material_fields if f.path == "quantity")
    assert (qty.previous_value, qty.proposal_previous_value, qty.value) == ("5", "7", "9")
    assert qty.comparison == "current" and qty.changed
    assert qty.label == "Quantity" and p.display_title == "Amend Record"
    assert p.canonical_proposal == {"arguments": action().arguments}
    assert p.digest == "unchanged"


def test_missing_unrelated_or_ambiguous_baseline_stays_unknown() -> None:
    for facts in ((), (fact(ref="record:other"),), (fact(), fact("6"))):
        qty = next(f for f in present(facts).material_fields if f.path == "quantity")
        assert qty.previous_value is None
        assert qty.proposal_previous_value == "7"
        assert qty.comparison == "current"


def test_plain_presentation_keeps_existing_proposal_comparison() -> None:
    a = action()
    p = presentation_for(
        a,
        run_revision=3,
        canonical_proposal={"arguments": a.arguments},
        findings=(),
        expires_at=NOW,
        previous_arguments={"quantity": "7"},
    )
    qty = next(f for f in p.material_fields if f.path == "quantity")
    assert qty.previous_value == "7" and qty.comparison == "proposal"
