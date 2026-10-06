"""ERP-07: create a CRM lead with a valid owner/team/source assignment."""

from __future__ import annotations

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.context import TaskContext
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.sdk.ports import ScopedReader, ValidationInput
from e_agent.sdk.validation import ResourceRef, Term, ValidationDataset
from pydantic import ValidationError

from ..common import PROPOSAL, DatasetWriter, check, num_check, ref_iri, report
from . import CONTACT_READ, CREATE_LEAD, LEAD_READ, TEAMS_READ
from .api import Contact, CreateLead, LeadView, Teams

CRM = "https://e-agent.dev/ns/crm#"
LEAD_RULES = ("CL-001", "CL-002", "CL-003", "CL-004")
LEAD_SHAPES = ResourceRef(package="e_agent.erp.crm", path="shapes/lead-shapes.ttl")
LEAD_BUNDLE = "crm-lead-rules@0.1.0"


class LeadDatasetBuilder:
    builder_id = "crm-lead-dataset"

    def supports(self, contract_id: str) -> bool:
        return contract_id == CREATE_LEAD

    def build(self, ctx: TaskContext, item: ValidationInput) -> ValidationDataset:
        w = DatasetWriter(CRM, CREATE_LEAD, LEAD_SHAPES, LEAD_BUNDLE, LEAD_RULES)
        try:
            lead = CreateLead.model_validate(item.proposal.arguments)
        except ValidationError:
            return w.incomplete(["well-formed lead arguments"])
        contacts = [
            Contact.model_validate(o.data)
            for o in item.observations
            if o.contract_id == CONTACT_READ and o.data
        ]
        teams = next(
            (
                Teams.model_validate(o.data)
                for o in item.observations
                if o.contract_id == TEAMS_READ
            ),
            None,
        )
        contact = next((c for c in contacts if c.contact_ref == lead.contact_ref), None)
        missing = [n for n, v in (("contact", contact), ("teams and sources", teams)) if v is None]
        if missing or contact is None or teams is None:
            return w.incomplete(missing or ["contact or teams"])
        w.typed(PROPOSAL, "LeadProposal")
        w.add(PROPOSAL, "expectedRevenue", Term.lit(lead.expected_revenue, "decimal"))
        w.add(PROPOSAL, "owner", Term.iri(ref_iri("user", lead.owner_ref)))
        c = ref_iri("contact", contact.contact_ref)
        w.add(PROPOSAL, "contact", Term.iri(c))
        w.add(c, "active", Term.lit("true" if contact.active else "false", "boolean"))
        team = next((t for t in teams.teams if t.team_ref == lead.team_ref), None)
        if team is not None:
            t = ref_iri("team", team.team_ref)
            w.add(PROPOSAL, "team", Term.iri(t))
            for member in team.member_refs:
                w.add(t, "member", Term.iri(ref_iri("user", member)))
        if lead.source_ref is not None:
            w.add(PROPOSAL, "sourceGiven", Term.lit("true", "boolean"))
            if any(s.source_ref == lead.source_ref for s in teams.sources):
                w.add(PROPOSAL, "source", Term.iri(ref_iri("source", lead.source_ref)))
        return w.dataset()


class LeadVerifier:
    verifier_id = "crm.lead-verifier"

    def supports(self, contract_id: str) -> bool:
        return contract_id == CREATE_LEAD

    async def verify(
        self,
        ctx: TaskContext,
        action: ActionRecord,
        receipt: ExecutionReceipt | None,
        reader: ScopedReader,
    ) -> OutcomeReport:
        if receipt is None:
            raise ValueError("leads are verified against a receipt")
        want = CreateLead.model_validate(action.arguments)
        obs = await reader.read(LEAD_READ, {"operation_key": action.logical_operation_id})
        leads = [LeadView.model_validate(o) for o in obs.data.get("leads", [])]
        checks = [check("exactly_one_lead", 1, len(leads))]
        if len(leads) == 1:
            got = leads[0]
            checks += [
                check(
                    "external_ref_matches_receipt",
                    ",".join(receipt.external_refs),
                    got.external_ref,
                ),
                check("name", want.name, got.name),
                check("contact", want.contact_ref, got.contact_ref),
                check("team", want.team_ref, got.team_ref),
                check("owner", want.owner_ref, got.owner_ref),
                check("source", want.source_ref, got.source_ref),
                num_check("expected_revenue", want.expected_revenue, got.expected_revenue),
            ]
        return report(ctx, action, self.verifier_id, checks, [obs.evidence.evidence_id])
