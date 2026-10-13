"""Backend-neutral validation datasets (MVP design §5, ADR 0009).

A domain pack turns a proposal and its observations into typed statements plus
references to its packaged shape assets. Validation engines (SHACL, ...) map the
dataset to their own representation; domains never handle RDF library objects
and engines never import domain code.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from e_agent.contracts.common import Record
from e_agent.contracts.context import TaskContext
from e_agent.contracts.validation import Finding

from .ports import ValidationInput

Datatype = Literal["string", "decimal", "boolean", "date", "dateTime"]


class Term(Record):
    kind: Literal["iri", "literal"]
    value: str
    datatype: Datatype | None = None

    @staticmethod
    def iri(value: str) -> Term:
        return Term(kind="iri", value=value)

    @staticmethod
    def lit(value: str, datatype: Datatype = "string") -> Term:
        return Term(kind="literal", value=value, datatype=datatype)


class Statement(Record):
    subject: str
    predicate: str
    object: Term


class ResourceRef(Record):
    """A packaged resource, read through importlib.resources (never cwd)."""

    package: str
    path: str


class ValidationDataset(Record):
    contract_id: str
    statements: tuple[Statement, ...]
    shapes: tuple[ResourceRef, ...]
    rule_bundle_version: str
    expected_rules: tuple[str, ...]
    """Rules evaluated by this engine; rules without violations are reported PASS."""
    complete: bool = True
    """False when required facts are missing: unviolated rules are then UNKNOWN, not PASS."""
    extra_findings: tuple[Finding, ...] = ()
    """Findings computed outside the engine (e.g. normalizer diagnostics)."""


@runtime_checkable
class ValidationDatasetBuilder(Protocol):
    builder_id: str

    def supports(self, contract_id: str) -> bool: ...

    def build(self, ctx: TaskContext, item: ValidationInput) -> ValidationDataset: ...
