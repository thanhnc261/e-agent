"""Field data classes beside the schema, and the stored record kinds (ADR 0030, Task 3b.3)."""

from typing import Any

import pytest
from e_agent.contracts.capability import CapabilityDescriptor
from e_agent.contracts.data_classes import (
    RECORD_KINDS,
    UNMARKED_CLASS,
    ClassIndex,
    DataClass,
    RecordClass,
    RetentionClass,
    leaf_property_pointers,
    parse_pointer,
    record_kind,
    resolve_property,
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
            "name": {"type": "string", "examples": [{"properties": {"x": {}}}]},
            "note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "lines": {"type": "array", "items": {"$ref": "#/$defs/Line"}},
            "a/b": {"type": "string"},
        },
    },
}
PERSON = {"type": "object", "properties": {"token": {"type": "string"}, "nick": {}}}
ALIASED: dict[str, Any] = {
    "output": {
        "$defs": {"Person": PERSON},
        "type": "object",
        "properties": {
            "person": {"$ref": "#/$defs/Person"},
            "other": {"$ref": "#/$defs/Person", "properties": {"extra": {"type": "string"}}},
            "tags": {"type": "object", "additionalProperties": {"$ref": "#/$defs/Person"}},
        },
    }
}
TOKEN = "/output/properties/person/properties/token"
DEFS_TOKEN = "/output/$defs/Person/properties/token"


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
    index = ClassIndex(DOCUMENT, {"/output/properties/name": DataClass.INTERNAL})
    assert UNMARKED_CLASS is DataClass.PERSONAL
    assert index.class_of("/output/properties/name") is DataClass.INTERNAL
    assert index.class_of("/output/properties/note") is DataClass.PERSONAL
    assert index.class_of("/input/properties/partner_ref") is DataClass.PERSONAL
    assert index.class_of("/output/properties/not-in-schema") is DataClass.PERSONAL
    unmarked = index.unmarked()
    assert "/output/properties/name" not in unmarked
    assert "/output/properties/note" in unmarked
    print(f"unmarked leaf properties: {len(unmarked)}")
    assert len(unmarked) == len(leaf_property_pointers(DOCUMENT)) - 1
    assert index.unmarked_counts() == {"input": 1, "output": 4}


def test_a_missing_schema_side_counts_none_not_zero() -> None:
    classes = {"/input/properties/partner_ref": DataClass.INTERNAL}
    index = ClassIndex({"input": DOCUMENT["input"]}, classes)
    assert index.unmarked_counts() == {"input": 0, "output": None}


def test_items_step_classes_every_array_element_through_a_ref() -> None:
    email = "/output/properties/lines/items/properties/email"
    assert resolve_property(DOCUMENT, email) == ("output", "$defs", "Line", "properties", "email")
    index = ClassIndex(
        DOCUMENT, {email: DataClass.PERSONAL, "/output/properties/lines": DataClass.INTERNAL}
    )
    assert index.class_of(email) is DataClass.PERSONAL
    # a container class covers the rest of its subtree
    assert index.class_of("/output/properties/lines/items/properties/ref") is DataClass.INTERNAL
    assert email not in index.unmarked()
    assert "/output/properties/lines/items/properties/ref" not in index.unmarked()


def test_a_deeper_declaration_never_lowers_a_class() -> None:
    index = ClassIndex(
        ALIASED,
        {"/output/properties/person": DataClass.SECRET, TOKEN: DataClass.INTERNAL},
    )
    assert index.class_of(TOKEN) is DataClass.SECRET


@pytest.mark.parametrize(("declared", "looked_up"), [(DEFS_TOKEN, TOKEN), (TOKEN, DEFS_TOKEN)])
def test_a_ref_alias_reaches_the_same_class(declared: str, looked_up: str) -> None:
    """C3-1: a class under ``$defs`` applies through every path that references it."""
    index = ClassIndex(ALIASED, {declared: DataClass.SECRET})
    assert index.class_of(looked_up) is DataClass.SECRET
    assert index.class_of("/output/properties/other/properties/token") is DataClass.SECRET
    assert index.class_of("/output/properties/tags/additionalProperties/properties/token") is (
        DataClass.SECRET
    )
    assert TOKEN not in index.unmarked()


def test_two_pointers_reaching_one_schema_with_different_classes_fail() -> None:
    with pytest.raises(ValueError, match="classed differently"):
        ClassIndex(ALIASED, {TOKEN: DataClass.SECRET, DEFS_TOKEN: DataClass.INTERNAL})
    same = ClassIndex(ALIASED, {TOKEN: DataClass.SECRET, DEFS_TOKEN: DataClass.SECRET})
    assert same.class_of(TOKEN) is DataClass.SECRET


def test_ref_with_sibling_properties_and_additional_properties_are_walked() -> None:
    """C3-3 and C3-4: both the ``$ref`` and its sibling ``properties`` count, and so do
    properties under ``additionalProperties``."""
    leaves = leaf_property_pointers(ALIASED)
    for pointer in (
        "/output/properties/other/properties/extra",
        "/output/properties/other/properties/token",
        "/output/properties/tags/additionalProperties/properties/nick",
    ):
        assert pointer in leaves, pointer
        assert resolve_property(ALIASED, pointer) is not None, pointer
    print(f"leaf property pointers: {len(leaves)}")
    assert len(leaves) == len(set(leaves)) == 7


def test_leaf_pointers_resolve_and_escape_per_rfc_6901() -> None:
    leaves = leaf_property_pointers(DOCUMENT)
    assert "/output/properties/a~1b" in leaves
    assert "/output/properties/lines" not in leaves  # a container, not a leaf
    assert all(resolve_property(DOCUMENT, p) is not None for p in leaves)
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
        # C3-5: data keywords are not schema context
        "/output/properties/name/examples/0/properties/x",
        "/output/properties/name/default/properties/x",
        "/output/properties/name/const/properties/x",
        "/output/properties/name/enum/0/properties/x",
        # C3-6: non-canonical array tokens
        "/output/properties/note/anyOf/00/properties/x",
        "/output/properties/note/anyOf/+0/properties/x",
        "/output/properties/note/anyOf/-1/properties/x",
    ],
)
def test_a_pointer_must_name_a_property_schema(pointer: str) -> None:
    assert resolve_property(DOCUMENT, pointer) is None
    with pytest.raises(ValueError, match="names no property schema"):
        ClassIndex(DOCUMENT, {pointer: DataClass.INTERNAL})


@pytest.mark.parametrize("pointer", ["/output/properties/a~2b", "/output/properties/a~", "/x~y"])
def test_a_malformed_escape_is_refused(pointer: str) -> None:
    """C3-6: a ``~`` not followed by 0 or 1 is malformed (RFC 6901)."""
    with pytest.raises(ValueError, match="escape"):
        parse_pointer(pointer)
    assert resolve_property(DOCUMENT, pointer) is None
    with pytest.raises(ValidationError):
        _capability(data_classes={pointer: "internal"})


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
