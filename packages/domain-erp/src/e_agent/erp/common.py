"""Helpers shared by the ERP bounded contexts (no domain knowledge here).

Bounded contexts stay independent of each other (ADR 0002); they may all use
this module, which depends only on contracts and the SDK.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal
from urllib.parse import quote

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.common import format_decimal, utc_now
from e_agent.contracts.context import TaskContext
from e_agent.contracts.outcome import OutcomeCheck, OutcomeReport, OutcomeStatus
from e_agent.sdk.validation import ResourceRef, Statement, Term, ValidationDataset

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
PROPOSAL = "urn:e-agent:proposal"


def ref_iri(kind: str, ref: str) -> str:
    return f"urn:e-agent:{kind}:{quote(ref, safe='')}"


def check(name: str, expected: object, observed: object) -> OutcomeCheck:
    return OutcomeCheck(
        name=name, passed=expected == observed, expected=str(expected), observed=str(observed)
    )


def num_check(name: str, expected: Decimal | str, observed: str | None) -> OutcomeCheck:
    want = Decimal(expected)
    ok = observed is not None and Decimal(observed) == want
    return OutcomeCheck(name=name, passed=ok, expected=format_decimal(want), observed=str(observed))


def report(
    ctx: TaskContext,
    action: ActionRecord,
    verifier_id: str,
    checks: Sequence[OutcomeCheck],
    refs: Iterable[str],
    version: str = "1",
) -> OutcomeReport:
    ok = bool(checks) and all(c.passed for c in checks)
    return OutcomeReport(
        run_id=ctx.run_id,
        action_id=action.action_id,
        status=OutcomeStatus.VERIFIED if ok else OutcomeStatus.FAILED,
        checks=tuple(checks),
        verifier_id=verifier_id,
        verifier_version=version,
        observed_refs=tuple(refs),
        reported_at=utc_now(),
    )


class DatasetWriter:
    """Collects statements for one proposal in a namespace; never defaults facts."""

    def __init__(
        self, ns: str, contract_id: str, shapes: ResourceRef, bundle: str, rules: tuple[str, ...]
    ):
        self.ns = ns
        self.contract_id = contract_id
        self.shapes = (shapes,)
        self.bundle = bundle
        self.rules = rules
        self.statements: list[Statement] = []

    def add(self, subject: str, predicate: str, obj: Term) -> None:
        self.statements.append(
            Statement(subject=subject, predicate=self.ns + predicate, object=obj)
        )

    def typed(self, subject: str, cls: str) -> None:
        self.statements.append(
            Statement(subject=subject, predicate=RDF_TYPE, object=Term.iri(self.ns + cls))
        )

    def dataset(self) -> ValidationDataset:
        return ValidationDataset(
            contract_id=self.contract_id,
            statements=tuple(self.statements),
            shapes=self.shapes,
            rule_bundle_version=self.bundle,
            expected_rules=self.rules,
        )

    def incomplete(self, missing: Iterable[str]) -> ValidationDataset:
        """Only the missing-fact rule is evaluated; every other rule stays UNKNOWN."""
        self.statements = []
        self.typed(PROPOSAL, "IncompleteProposal")
        for m in missing:
            self.add(PROPOSAL, "missingFact", Term.lit(m))
        return ValidationDataset(
            contract_id=self.contract_id,
            statements=tuple(self.statements),
            shapes=self.shapes,
            rule_bundle_version=self.bundle,
            expected_rules=self.rules,
            complete=False,
        )
