"""Maps a ValidationDataset to RDF, runs pySHACL and returns canonical findings.

Rule identity comes from the shapes themselves: every rule shape carries
``ea:ruleId`` (and optionally ``ea:ruleVersion`` and ``ea:onFail "UNKNOWN"``
for missing-fact checks), so prompts or code never hold a second copy of the rule.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from importlib.resources import files

from e_agent.contracts.context import TaskContext
from e_agent.contracts.validation import Finding, ValidationResult, ValidationStatus
from e_agent.sdk.ports import ValidationInput
from e_agent.sdk.validation import (
    ResourceRef,
    Statement,
    ValidationDataset,
    ValidationDatasetBuilder,
)
from pyshacl import validate as shacl_validate
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, SH, XSD
from rdflib.term import Node

EA = Namespace("https://e-agent.dev/ns/core#")
_XSD = {
    "string": XSD.string,
    "decimal": XSD.decimal,
    "boolean": XSD.boolean,
    "date": XSD.date,
    "dateTime": XSD.dateTime,
}
ENGINE_ID = "shacl-pyshacl"


class ShaclEngineError(RuntimeError):
    pass


def to_graph(statements: Iterable[Statement]) -> Graph:
    graph = Graph()
    for st in statements:
        obj: Node
        if st.object.kind == "iri":
            obj = URIRef(st.object.value)
        else:
            obj = Literal(st.object.value, datatype=_XSD[st.object.datatype or "string"])
        graph.add((URIRef(st.subject), URIRef(st.predicate), obj))
    return graph


class ShaclPlanValidator:
    """PlanValidator that delegates dataset construction to domain builders."""

    validator_id = ENGINE_ID

    def __init__(self, builders: Sequence[ValidationDatasetBuilder]) -> None:
        self._builders = list(builders)
        self._shapes_cache: dict[tuple[ResourceRef, ...], Graph] = {}

    def supports(self, contract_id: str) -> bool:
        return any(b.supports(contract_id) for b in self._builders)

    def _builder(self, contract_id: str) -> ValidationDatasetBuilder:
        matches = [b for b in self._builders if b.supports(contract_id)]
        if len(matches) != 1:
            raise ShaclEngineError("no unique dataset builder for contract")
        return matches[0]

    def shapes_graph(self, refs: tuple[ResourceRef, ...]) -> Graph:
        cached = self._shapes_cache.get(refs)
        if cached is not None:
            return cached
        graph = Graph()
        for ref in refs:
            text = files(ref.package).joinpath(ref.path).read_text("utf-8")
            graph.parse(data=text, format="turtle")
        self._shapes_cache[refs] = graph
        return graph

    async def validate(self, ctx: TaskContext, item: ValidationInput) -> ValidationResult:
        dataset = self._builder(item.proposal.contract_id).build(ctx, item)
        return self.validate_dataset(dataset)

    def validate_dataset(self, dataset: ValidationDataset) -> ValidationResult:
        shapes = self.shapes_graph(dataset.shapes)
        data = to_graph(dataset.statements)
        conforms, report, _ = shacl_validate(
            data,
            shacl_graph=shapes,
            inference="none",
            abort_on_first=False,
            allow_warnings=False,
            advanced=False,
            meta_shacl=False,
        )
        if not isinstance(report, Graph):  # pragma: no cover - pyshacl contract
            raise ShaclEngineError("unexpected report type")
        violations: dict[str, list[Finding]] = {}
        for result in report.subjects(RDF.type, SH.ValidationResult):
            rule_id, version, on_fail = self._rule_of(shapes, report, result)
            if rule_id is None:
                raise ShaclEngineError("violation from a shape without ea:ruleId")
            message = report.value(result, SH.resultMessage)
            value = report.value(result, SH.value)
            status = ValidationStatus.UNKNOWN if on_fail == "UNKNOWN" else ValidationStatus.FAIL
            violations.setdefault(rule_id, []).append(
                Finding(
                    rule_id=rule_id,
                    rule_version=version,
                    status=status,
                    message=str(message) if message is not None else "constraint violated",
                    observed=_short(value),
                )
            )
        findings: list[Finding] = list(dataset.extra_findings)
        for rule_id in dataset.expected_rules:
            if rule_id in violations:
                findings.extend(violations.pop(rule_id))
            else:
                findings.append(
                    Finding(
                        rule_id=rule_id,
                        rule_version="1",
                        status=ValidationStatus.PASS
                        if dataset.complete
                        else ValidationStatus.UNKNOWN,
                        message="satisfied" if dataset.complete else "not evaluated: facts missing",
                    )
                )
        for extra in violations.values():  # violations of rules not declared as expected
            findings.extend(extra)
        statuses = {f.status for f in findings}
        overall = next(
            (
                s
                for s in (ValidationStatus.ERROR, ValidationStatus.FAIL, ValidationStatus.UNKNOWN)
                if s in statuses
            ),
            ValidationStatus.PASS,
        )
        if conforms and overall is ValidationStatus.FAIL and not dataset.extra_findings:
            raise ShaclEngineError("engine conformance disagrees with findings")
        return ValidationResult(
            status=overall,
            findings=tuple(findings),
            rule_bundle_version=dataset.rule_bundle_version,
            validator_id=self.validator_id,
        )

    @staticmethod
    def _rule_of(shapes: Graph, report: Graph, result: Node) -> tuple[str | None, str, str | None]:
        candidates: list[Node] = []
        for prop in (SH.sourceConstraint, SH.sourceShape):
            node = report.value(result, prop)
            if node is not None:
                candidates.append(node)
        # property shapes are often blank nodes: walk up to the owning node shape
        for node in list(candidates):
            candidates.extend(shapes.subjects(SH.property, node))
        on_fail = next(
            (str(v) for n in candidates if (v := shapes.value(n, EA.onFail)) is not None), None
        )
        for node in candidates:
            rule = shapes.value(node, EA.ruleId)
            if rule is not None:
                version = shapes.value(node, EA.ruleVersion)
                return str(rule), str(version or "1"), on_fail
        return None, "1", None


def _short(node: Node | None) -> str | None:
    if node is None or isinstance(node, BNode):
        return None
    return str(node)
