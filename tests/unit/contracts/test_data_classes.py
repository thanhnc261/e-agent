"""Field data classes beside the schema, and the stored record kinds (ADR 0030, Task 3b.3)."""

from typing import Any

import pytest
from e_agent.contracts.capability import CapabilityDescriptor
from e_agent.contracts.data_classes import (
    RECORD_KINDS,
    UNMARKED_CLASS,
    DataClass,
    RecordClass,
    RetentionClass,
    class_of,
    leaf_property_pointers,
    record_kind,
    resolve_property,
    unmarked_pointers,
)
from pydantic import ValidationError

LINE = {
    "type": "object",
    "properties": {"ref": {"type": "string"}, "email": {"type": "string"}},
}
DOCUMENT: dict[str, Any] = {
    "input": {"type": "object", "properties": {"partner_ref": {"type": "string"}}},
    "output": {
        "$defs": {"Line": LINE},
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "lines": {"type": "array", "items": {"$ref": "#/$defs/Line"}},
            "a/b": {"type": "string"},
        },
    },
}


def _capability(**declared: Any) -> CapabilityDescriptor:
    return CapabilityDescriptor.model_validate(
        {
            "contract_id": "notes.note.read.v1",
            "effect": "read",
            "input_schema_id": "in",
            "output_schema_id": "out",
            **declared,
        }
    )


def test_unmarked_property_counts_as_personal() -> None:
    classes = {"/output/properties/name": DataClass.INTERNAL}
    assert UNMARKED_CLASS is DataClass.PERSONAL
    assert class_of(classes, "/output/properties/name") is DataClass.INTERNAL
    assert class_of(classes, "/output/properties/note") is DataClass.PERSONAL
    assert class_of({}, "/input/properties/partner_ref") is DataClass.PERSONAL
    unmarked = unmarked_pointers(DOCUMENT, classes)
    assert "/output/properties/name" not in unmarked
    assert "/output/properties/note" in unmarked
    print(f"unmarked leaf properties: {len(unmarked)}")
    assert len(unmarked) == len(leaf_property_pointers(DOCUMENT)) - 1


def test_items_step_classes_every_array_element_through_a_ref() -> None:
    email = "/output/properties/lines/items/properties/email"
    assert resolve_property(DOCUMENT, email) == {"type": "string"}
    classes = {email: DataClass.PERSONAL, "/output/properties/lines": DataClass.INTERNAL}
    # the deeper pointer wins; a container pointer classes the rest of its subtree
    assert class_of(classes, email) is DataClass.PERSONAL
    assert class_of(classes, "/output/properties/lines/items/properties/ref") is (
        DataClass.INTERNAL
    )
    assert email not in unmarked_pointers(DOCUMENT, classes)
    assert "/output/properties/lines/items/properties/ref" not in unmarked_pointers(
        DOCUMENT, classes
    )


def test_leaf_pointers_resolve_and_escape_per_rfc_6901() -> None:
    leaves = leaf_property_pointers(DOCUMENT)
    assert "/output/properties/a~1b" in leaves
    assert "/output/properties/lines" not in leaves  # a container, not a leaf
    assert all(resolve_property(DOCUMENT, p) is not None for p in leaves)
    print(f"leaf property pointers: {len(leaves)}")
    assert len(leaves) == 6


@pytest.mark.parametrize(
    "pointer",
    [
        "/output",
        "/output/properties",
        "/output/properties/missing",
        "/output/properties/lines/items",
        "/output/type",
        "/result/properties/name",
        "/output/properties/lines/items/properties/ref/extra",
    ],
)
def test_a_pointer_must_name_a_property_schema(pointer: str) -> None:
    assert resolve_property(DOCUMENT, pointer) is None


def test_pointer_into_an_absent_schema_names_nothing() -> None:
    assert resolve_property({"input": DOCUMENT["input"]}, "/output/properties/name") is None


def test_descriptor_declares_classes_beside_the_schema() -> None:
    declared = _capability(data_classes={"/output/properties/name": "personal"})
    assert declared.data_classes == {"/output/properties/name": DataClass.PERSONAL}
    assert _capability().data_classes == {}  # an existing declaration still loads
    # it stays hashable, as registration compares declared capability sets
    assert len({declared, _capability(data_classes={"/output/properties/name": "personal"})}) == 1
    assert declared != _capability()


@pytest.mark.parametrize(
    "bad",
    [
        {"/output/properties/name": "confidential"},
        {"output/properties/name": "internal"},
        {"/result/properties/name": "internal"},
        {"/output": "internal"},
    ],
)
def test_descriptor_rejects_bad_class_declarations(bad: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        _capability(data_classes=bad)


def test_record_kinds_are_declared_once_with_both_classes() -> None:
    assert RECORD_KINDS, "no record kinds declared"
    for name, kind in RECORD_KINDS.items():
        assert kind.kind == name
        assert isinstance(kind.record_class, RecordClass)
        assert isinstance(kind.retention, RetentionClass)
        assert kind.holds
    print(f"record kinds declared: {len(RECORD_KINDS)}")
    assert record_kind("runs").record_class is RecordClass.AUDIT_SKELETON
    assert record_kind("continuations").record_class is RecordClass.BUSINESS_PAYLOAD
    assert record_kind("run_work").record_class is RecordClass.INFRA
    with pytest.raises(KeyError):
        record_kind("unknown")
