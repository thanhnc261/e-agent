"""Field data classes beside the schema, and the stored record kinds (ADR 0030, Task 3b.3)."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

import pytest
from e_agent.contracts.capability import CapabilityDescriptor
from e_agent.contracts.common import Record
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
    unsupported_construct,
)
from pydantic import Field, ValidationError

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
            "other": {"$ref": "#/$defs/Person", "description": "an annotation sibling"},
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


def test_additional_properties_are_walked_and_counted() -> None:
    """C3-4 (round 1): properties under ``additionalProperties`` are leaves, resolve and
    count when unmarked."""
    leaves = leaf_property_pointers(ALIASED)
    nick = "/output/properties/tags/additionalProperties/properties/nick"
    assert nick in leaves
    assert resolve_property(ALIASED, nick) == ("output", "$defs", "Person", "properties", "nick")
    assert nick in ClassIndex(ALIASED, {}).unmarked()
    print(f"leaf property pointers: {len(leaves)}")
    assert len(leaves) == len(set(leaves)) == 6


def _output(properties: dict[str, Any], **root: Any) -> dict[str, Any]:
    return {"output": {"type": "object", "properties": properties, **root}}


DEFS = {"$defs": {"Person": PERSON, "U": {"anyOf": [PERSON, {"type": "null"}]}}}
UNSUPPORTED = {
    # round 1 C3-3: a $ref beside sibling properties
    "C3-3": _output({"other": {"$ref": "#/$defs/Person", "properties": {"extra": {}}}}, **DEFS),
    # round 2 C3-1: a terminal $ref into a definition, to one of its leaves
    "C3-1": _output(
        {"person": {"$ref": "#/$defs/Person"}, "tok": {"$ref": "#/$defs/Person/properties/token"}},
        **DEFS,
    ),
    # round 2 C3-7: a same-named sibling next to a $ref
    "C3-7": _output(
        {"person": {"$ref": "#/$defs/Person", "properties": {"token": {"type": "string"}}}},
        **DEFS,
    ),
    # round 2 C3-8: a $ref into an anyOf branch
    "C3-8": _output({"u": {"$ref": "#/$defs/U/anyOf/0"}}, **DEFS),
    # round 2 C3-9: then / else / patternProperties name property schemas, unsupported
    "C3-9-then": _output({"p": {"if": {}, "then": {"properties": {"token": {"type": "string"}}}}}),
    "C3-9-patternProperties": _output(
        {"p": {"patternProperties": {"^t": {"properties": {"token": {"type": "string"}}}}}}
    ),
    "nested-$defs": _output({"p": {"$defs": {"X": {}}, "type": "object"}}),
    "other-$ref": _output({"p": {"$ref": "https://example.com/schema"}}),
    "not": _output({"p": {"not": {"type": "string"}}}),
}
DECLARED = {
    "C3-3": "/output/properties/other/properties/extra",
    "C3-1": "/output/$defs/Person/properties/token",
    "C3-7": "/output/$defs/Person/properties/token",
    "C3-8": "/output/$defs/Person/properties/token",
    "C3-9-then": "/output/properties/p/then/properties/token",
    "C3-9-patternProperties": "/output/properties/p/patternProperties/^t/properties/token",
    "nested-$defs": "/output/properties/p",
    "other-$ref": "/output/properties/p",
    "not": "/output/properties/p",
}


@pytest.mark.parametrize("probe", sorted(UNSUPPORTED))
def test_a_declaration_on_an_unsupported_schema_is_refused(probe: str) -> None:
    """Every Codex probe that leaves the supported subset fails admission by design; the
    message names the side and the construct, never a value."""
    document = UNSUPPORTED[probe]
    assert unsupported_construct(document["output"]) is not None, probe
    with pytest.raises(ValueError, match="outside the supported subset") as err:
        ClassIndex(document, {DECLARED[probe]: DataClass.SECRET})
    assert "output schema" in str(err.value)


@pytest.mark.parametrize("probe", sorted(UNSUPPORTED))
def test_an_unsupported_side_classes_every_value_personal(probe: str) -> None:
    """With no declaration possible there, every value is personal and the side's count
    is None, with the construct listed."""
    index = ClassIndex(UNSUPPORTED[probe], {})
    assert index.class_of(DECLARED[probe]) is DataClass.PERSONAL
    assert index.unmarked_counts() == {"input": None, "output": None}
    assert set(index.unsupported) == {"output"}


def test_the_construct_is_named_by_keyword() -> None:
    assert unsupported_construct(UNSUPPORTED["C3-9-then"]["output"]) == "the keyword 'if'"
    assert unsupported_construct(UNSUPPORTED["C3-7"]["output"]) == (
        "a $ref beside the keyword 'properties'"
    )
    assert "#/$defs/<Name>" in str(unsupported_construct(UNSUPPORTED["C3-8"]["output"]))


def test_c3_7_a_ref_class_is_never_hidden() -> None:
    """Round 2 C3-7, in the supported subset: a $ref can have no schema-bearing sibling,
    so the class declared on the definition always applies through it."""
    document = _output({"person": {"$ref": "#/$defs/Person", "title": "P"}}, **DEFS)
    index = ClassIndex(document, {"/output/$defs/Person/properties/token": DataClass.SECRET})
    assert index.class_of("/output/properties/person/properties/token") is DataClass.SECRET


def test_c3_8_a_whole_definition_union_classes_its_branch() -> None:
    """Round 2 C3-8, supported form: a $ref to the whole union definition."""
    document = _output({"u": {"$ref": "#/$defs/U"}}, **DEFS)
    pointer = "/output/properties/u/anyOf/0/properties/token"
    index = ClassIndex(document, {"/output/$defs/U/anyOf/0/properties/token": DataClass.SECRET})
    assert index.class_of(pointer) is DataClass.SECRET
    assert index.class_of("/output/$defs/Person/properties/token") is DataClass.PERSONAL


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


class _Kind(StrEnum):
    A = "a"


class _Leaf(Record):
    token: str
    nick: str | None = None


class _Cat(Record):
    kind: Literal["cat"]
    leaf: _Leaf


class _Dog(Record):
    kind: Literal["dog"]
    leaves: tuple[_Leaf, ...]


class _Tree(Record):
    name: str
    children: tuple["_Tree", ...] = ()


class _Everything(Record):
    leaf: _Leaf
    maybe: _Leaf | None = None
    described: _Leaf = Field(description="a $ref with an annotation sibling")
    defaulted: _Leaf = _Leaf(token="t")
    by_name: dict[str, _Leaf]
    pair: tuple[str, int]
    pet: _Cat | _Dog = Field(discriminator="kind")
    union: _Leaf | int
    kind: _Kind
    tree: _Tree
    when: date
    amount: Decimal = Field(ge=0)
    tags: frozenset[str] = frozenset()


def test_pydantic_schemas_fall_inside_the_supported_subset() -> None:
    """The shapes pydantic v2's ``model_json_schema()`` emits: nested and optional models,
    annotated and defaulted refs, dicts, fixed tuples, discriminated and plain unions,
    enums, recursion and constrained scalars."""
    schema = _Everything.model_json_schema()
    assert unsupported_construct(schema) is None
    leaves = leaf_property_pointers({"output": schema})
    print(f"pydantic leaf properties: {len(leaves)}")
    assert "/output/properties/by_name/additionalProperties/properties/token" in leaves
    index = ClassIndex(
        {"output": schema}, {"/output/$defs/_Leaf/properties/token": DataClass.SECRET}
    )
    for pointer in (
        "/output/properties/leaf/properties/token",
        "/output/properties/described/properties/token",
        "/output/properties/maybe/anyOf/0/properties/token",
        "/output/properties/by_name/additionalProperties/properties/token",
    ):
        assert index.class_of(pointer) is DataClass.SECRET, pointer
