"""Generic SHACL engine behaviour, independent of any domain."""

import pytest
from e_agent.adapters.shacl.engine import ShaclEngineError, ShaclPlanValidator
from e_agent.contracts.validation import ValidationStatus
from e_agent.sdk.validation import ResourceRef, Statement, Term, ValidationDataset
from rdflib import Graph

EX = "https://example.test/"
SHAPES = f"""
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ea: <https://e-agent.dev/ns/core#> .
@prefix ex: <{EX}> .
ex:R1 a sh:NodeShape ; ea:ruleId "R-1" ; sh:targetClass ex:Thing ;
  sh:property [ sh:path ex:name ; sh:minCount 1 ] .
ex:R2 a sh:NodeShape ; ea:ruleId "R-2" ; ea:onFail "UNKNOWN" ; sh:targetClass ex:Thing ;
  sh:property [ sh:path ex:missing ; sh:maxCount 0 ] .
ex:Anon a sh:NodeShape ; sh:targetClass ex:Odd ; sh:property [ sh:path ex:x ; sh:minCount 1 ] .
"""
REF = (ResourceRef(package="inline", path="shapes.ttl"),)


def _validator() -> ShaclPlanValidator:
    v = ShaclPlanValidator([])
    v._shapes_cache[REF] = Graph().parse(data=SHAPES, format="turtle")
    return v


def _ds(*statements: tuple[str, str, Term]) -> ValidationDataset:
    return ValidationDataset(
        contract_id="x.y.z.v1",
        statements=tuple(Statement(subject=s, predicate=p, object=o) for s, p, o in statements),
        shapes=REF,
        rule_bundle_version="test@1",
        expected_rules=("R-1", "R-2"),
    )


TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def test_conforming_data_reports_pass_for_every_expected_rule() -> None:
    result = _validator().validate_dataset(
        _ds((EX + "a", TYPE, Term.iri(EX + "Thing")), (EX + "a", EX + "name", Term.lit("n")))
    )
    assert result.status is ValidationStatus.PASS
    assert {f.rule_id for f in result.findings} == {"R-1", "R-2"}


def test_violation_maps_to_rule_id_from_owning_node_shape() -> None:
    result = _validator().validate_dataset(_ds((EX + "a", TYPE, Term.iri(EX + "Thing"))))
    assert result.status is ValidationStatus.FAIL
    assert [f.status for f in result.findings if f.rule_id == "R-1"] == [ValidationStatus.FAIL]


def test_missing_fact_rule_reports_unknown() -> None:
    result = _validator().validate_dataset(
        _ds(
            (EX + "a", TYPE, Term.iri(EX + "Thing")),
            (EX + "a", EX + "name", Term.lit("n")),
            (EX + "a", EX + "missing", Term.lit("stock")),
        )
    )
    assert result.status is ValidationStatus.UNKNOWN


def test_shape_without_rule_id_is_an_engine_error() -> None:
    with pytest.raises(ShaclEngineError):
        _validator().validate_dataset(_ds((EX + "b", TYPE, Term.iri(EX + "Odd"))))
