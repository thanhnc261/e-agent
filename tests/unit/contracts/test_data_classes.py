"""Field data classes keyed by instance path, and the stored record kinds (ADR 0030,
Task 3b.3; instance-path keys by owner decision 2026-10-19).

A value's class is the most restrictive class declared on its instance path or an
ancestor path, ``personal`` when none. Lookup never walks a schema; schemas serve
admission (the path must exist) and readiness counts only.
"""

import random
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

import pytest
from e_agent.contracts.capability import CapabilityDescriptor
from e_agent.contracts.common import Record
from e_agent.contracts.data_classes import (
    RECORD_KINDS,
    RESTRICTIVENESS,
    UNMARKED_CLASS,
    DataClass,
    RecordClass,
    RetentionClass,
    check_class_key,
    check_declarations,
    class_for,
    format_pointer,
    leaf_instance_paths,
    most_restrictive,
    parse_pointer,
    record_kind,
    unmarked_counts,
    unsupported_construct,
    unsupported_sides,
)
from pydantic import Field, ValidationError

S, INT, P = DataClass.SECRET, DataClass.INTERNAL, DataClass.PERSONAL


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


def _output(properties: dict[str, Any], **root: Any) -> dict[str, Any]:
    return {"output": {"type": "object", "properties": properties, **root}}


# -- lookup: string work over declared paths -----------------------------------------------
def test_unmarked_property_counts_as_personal() -> None:
    classes = {"/output/name": INT}
    assert UNMARKED_CLASS is P
    assert class_for(classes, "/output/name") is INT
    assert class_for(classes, "/output/note") is P
    assert class_for({}, "/input/partner_ref") is P
    assert class_for(classes, "/output") is P


def test_an_index_is_written_items_and_a_dict_is_classed_by_its_property() -> None:
    classes = {"/output/lines/items/email": P, "/output/lines": INT, "/output/tags": S}
    assert class_for(classes, "/output/lines/0/email") is P
    assert class_for(classes, "/output/lines/12/email") is P
    assert class_for(classes, "/output/lines/items/email") is P
    assert class_for(classes, "/output/lines/3/ref") is INT  # the container's class
    # keys of a dict-valued property are data: the dict property classes all of it
    assert class_for(classes, "/output/tags/any key/deeper") is S
    assert class_for(classes, "/output/tags/0") is S


def test_the_most_restrictive_declaration_wins() -> None:
    classes = {"/output/person": S, "/output/person/token": INT, "/output/a": INT, "/output/a/b": S}
    assert class_for(classes, "/output/person/token") is S  # a deeper key never lowers
    assert class_for(classes, "/output/a/b") is S
    assert class_for(classes, "/output/a/c") is INT
    assert most_restrictive([]) is None


@pytest.mark.parametrize(
    "key",
    [
        "output/name",  # not a pointer
        "/result/name",  # not under /input or /output
        "/output",  # names the whole side, not a property
        "/output//name",  # empty token
        "/output/name/",  # empty token
        "/output/lines/0/email",  # an index is written `items`
        "/output/a~2b",  # malformed escape
        "/output/a~",  # malformed escape
    ],
)
def test_a_malformed_key_is_refused(key: str) -> None:
    with pytest.raises(ValueError, match=r"pointer|key"):
        check_class_key(key)
    with pytest.raises(ValidationError):
        _capability(data_classes={key: "internal"})


def test_rfc_6901_escapes_round_trip() -> None:
    assert parse_pointer("/output/a~1b/c~0d") == ("output", "a/b", "c~d")
    assert format_pointer(("output", "a/b", "c~d")) == "/output/a~1b/c~0d"
    assert class_for({"/output/a~1b": S}, "/output/a~1b/0") is S


def test_descriptor_declares_classes_beside_the_schema() -> None:
    declared = _capability(data_classes={"/output/name": "personal"})
    assert declared.data_classes == {"/output/name": P}
    assert _capability().data_classes == {}  # an existing declaration still loads
    # it stays hashable, as registration compares declared capability sets
    assert len({declared, _capability(data_classes={"/output/name": "personal"})}) == 1
    assert declared != _capability()
    with pytest.raises(ValidationError):
        _capability(data_classes={"/output/name": "confidential"})


# -- the invariant: randomized shapes and declarations -------------------------------------
KEYS = ("a", "b", "name", "items", "x/y", "t~z", "email")
SEEDS = 300


def _shape(rng: random.Random, depth: int = 0) -> Any:
    roll = rng.random()
    if depth >= 4 or roll < 0.3:
        return rng.choice(("s", 1, None, True, 2.5))
    if roll < 0.65:
        return {k: _shape(rng, depth + 1) for k in rng.sample(KEYS, rng.randint(1, 3))}
    return [_shape(rng, depth + 1) for _ in range(rng.randint(0, 3))]


def _values(
    value: Any, concrete: tuple[str, ...], canonical: tuple[str, ...]
) -> Iterator[tuple[tuple[str, ...], tuple[str, ...]]]:
    """Every value's concrete path (real indices) and canonical path (``items``)."""
    yield concrete, canonical
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _values(child, (*concrete, key), (*canonical, key))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from _values(child, (*concrete, str(i)), (*canonical, "items"))


def _expected(
    value: Any,
    concrete: tuple[str, ...],
    canonical: tuple[str, ...],
    declared: dict[tuple[str, ...], DataClass],
    floor: DataClass | None,
) -> Iterator[tuple[tuple[str, ...], DataClass | None]]:
    """The oracle, independent of the implementation: walk the data top-down carrying
    the most restrictive class declared so far."""
    here = most_restrictive(c for c in (floor, declared.get(canonical)) if c is not None)
    yield concrete, here
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _expected(child, (*concrete, key), (*canonical, key), declared, here)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from _expected(child, (*concrete, str(i)), (*canonical, "items"), declared, here)


def test_a_value_class_is_never_lower_than_any_declaration_above_it() -> None:
    cases = 0
    for seed in range(SEEDS):
        rng = random.Random(seed)
        data = _shape(rng)
        canonical = sorted({c for _, c in _values(data, ("output",), ("output",)) if len(c) > 1})
        chosen = rng.sample(canonical, min(len(canonical), rng.randint(0, 4)))
        declared = {c: rng.choice(RESTRICTIVENESS) for c in chosen}
        classes = {format_pointer(c): k for c, k in declared.items()}
        for key in classes:
            check_class_key(key)
        for concrete, floor in _expected(data, ("output",), ("output",), declared, None):
            got = class_for(classes, format_pointer(concrete))
            want = UNMARKED_CLASS if floor is None else floor
            assert RESTRICTIVENESS.index(got) >= RESTRICTIVENESS.index(want), (seed, concrete)
            assert got is want, (seed, concrete, classes)
            cases += 1
    print(f"invariant cases: {cases} over {SEEDS} seeds")
    assert cases > 0, "0 cases is a failure (PR-31)"


# -- admission: a path must exist through at least one schema branch -----------------------
PERSON = {"type": "object", "properties": {"token": {"type": "string"}, "nick": {}}}
DEFS = {"$defs": {"Person": PERSON, "U": {"anyOf": [PERSON, {"type": "null"}]}}}


def test_admission_follows_properties_items_refs_and_branches() -> None:
    document = _output(
        {
            "person": {"$ref": "#/$defs/Person"},
            "maybe": {"anyOf": [{"$ref": "#/$defs/Person"}, {"type": "null"}]},
            "u": {"$ref": "#/$defs/U"},
            "list": {"type": "array", "items": {"$ref": "#/$defs/Person"}},
            "pair": {"type": "array", "prefixItems": [{"type": "string"}, PERSON]},
            "both": {"allOf": [{"properties": {"left": {}}}, {"properties": {"right": {}}}]},
        },
        **DEFS,
    )
    ok = [
        "/output/person/token",
        "/output/maybe/token",
        "/output/u/nick",
        "/output/list/items/token",
        "/output/pair/items/token",
        "/output/both/left",
        "/output/both/right",
        "/output/list",
    ]
    check_declarations(document, dict.fromkeys(ok, S))
    for bad in ("/output/person/missing", "/output/list/items", "/output/person/token/x"):
        with pytest.raises(ValueError, match="resolves to no property"):
            check_declarations(document, {bad: S})
    with pytest.raises(ValueError, match="resolves to no property"):
        check_declarations({}, {"/input/a": S})


def test_readiness_counts_leaves_and_treats_a_dict_as_a_leaf() -> None:
    document = _output(
        {
            "name": {"type": "string"},
            "lines": {"type": "array", "items": {"$ref": "#/$defs/Person"}},
            "by_name": {"type": "object", "additionalProperties": {"$ref": "#/$defs/Person"}},
        },
        **DEFS,
    )
    leaves = leaf_instance_paths(document)
    assert leaves == (
        "/output/name",
        "/output/lines/items/token",
        "/output/lines/items/nick",
        "/output/by_name",
    )
    assert unmarked_counts(document, {"/output/name": INT}) == {"input": None, "output": 3}
    assert (
        unmarked_counts(
            document, {"/output/lines": INT, "/output/name": INT, "/output/by_name": S}
        )["output"]
        == 0
    )


def test_a_recursive_schema_terminates() -> None:
    tree = {"properties": {"name": {}, "children": {"items": {"$ref": "#/$defs/T"}}}}
    document = _output({"tree": {"$ref": "#/$defs/T"}}, **{"$defs": {"T": tree}})
    assert "/output/tree/name" in leaf_instance_paths(document)
    check_declarations(document, {"/output/tree/children/items/children/items/name": S})


# -- every Codex probe of rounds 1-3, as instance paths ------------------------------------
UNSUPPORTED = {
    "r1-C3-3": _output({"other": {"$ref": "#/$defs/Person", "properties": {"extra": {}}}}, **DEFS),
    "r2-C3-1": _output({"tok": {"$ref": "#/$defs/Person/properties/token"}}, **DEFS),
    "r2-C3-7": _output(
        {"person": {"$ref": "#/$defs/Person", "properties": {"token": {"type": "string"}}}},
        **DEFS,
    ),
    "r2-C3-8": _output({"u": {"$ref": "#/$defs/U/anyOf/0"}}, **DEFS),
    "r2-C3-9-then": _output({"p": {"if": {}, "then": {"properties": {"token": {}}}}}),
    "r2-C3-9-patternProperties": _output(
        {"p": {"patternProperties": {"^t": {"properties": {"token": {}}}}}}
    ),
    "r3-C3-13": _output(
        {"person": {"$ref": "#/$defs/Per%73on"}},
        **{"$defs": {"Per%73on": {"properties": {"token": {}}}, "Person": PERSON}},
    ),
}
PROBE_PATH = {
    "r1-C3-3": "/output/other/extra",
    "r2-C3-1": "/output/tok",
    "r2-C3-7": "/output/person/token",
    "r2-C3-8": "/output/u/token",
    "r2-C3-9-then": "/output/p/token",
    "r2-C3-9-patternProperties": "/output/p/token",
    "r3-C3-13": "/output/person/token",
}


@pytest.mark.parametrize("probe", sorted(UNSUPPORTED))
def test_a_probe_outside_the_supported_subset_is_refused(probe: str) -> None:
    """Refused by design: a declaration on that side fails admission, the side is listed
    with its construct, and its count is None. Lookup, which never reads the schema,
    still gives the declared value its class, never lower."""
    document = UNSUPPORTED[probe]
    assert unsupported_construct(document["output"]) is not None
    assert set(unsupported_sides(document)) == {"output"}
    with pytest.raises(ValueError, match="outside the supported subset") as err:
        check_declarations(document, {PROBE_PATH[probe]: S})
    assert "output schema" in str(err.value)
    assert unmarked_counts(document, {}) == {"input": None, "output": None}
    assert class_for({PROBE_PATH[probe]: S}, PROBE_PATH[probe]) is S
    assert class_for({}, PROBE_PATH[probe]) is P


def test_r1_c3_1_a_value_under_a_ref_keeps_its_class() -> None:
    document = _output({"person": {"$ref": "#/$defs/Person"}}, **DEFS)
    classes = {"/output/person/token": S}
    check_declarations(document, classes)
    assert class_for(classes, "/output/person/token") is S


def test_r1_c3_4_a_dict_under_additional_properties_is_classed_by_its_property() -> None:
    document = _output({"tags": {"additionalProperties": {"$ref": "#/$defs/Person"}}}, **DEFS)
    classes = {"/output/tags": S}
    check_declarations(document, classes)
    assert class_for(classes, "/output/tags/k/token") is S
    assert unmarked_counts(document, {}) == {"input": None, "output": 1}


def test_r1_c3_5_a_data_keyword_is_not_a_path() -> None:
    document = _output({"name": {"type": "string", "examples": [{"x": 1}], "default": {}}})
    for key in ("/output/name/examples", "/output/name/default", "/output/name/x"):
        with pytest.raises(ValueError, match="resolves to no property"):
            check_declarations(document, {key: S})


def test_r1_c3_6_indices_and_escapes() -> None:
    classes = {"/output/lines/items/email": S}
    assert class_for(classes, "/output/lines/0/email") is S
    assert class_for(classes, "/output/lines/7/email") is S
    with pytest.raises(ValueError, match="escape"):
        class_for(classes, "/output/lines/0/e~2mail")
    with pytest.raises(ValueError, match="items"):
        check_class_key("/output/lines/00/email")


def test_r3_c3_10_overlapping_all_of_properties_keep_the_class() -> None:
    document = _output(
        {
            "v": {
                "allOf": [
                    {"properties": {"token": {"type": "string"}}},
                    {"properties": {"token": {}}},
                ]
            }
        }
    )
    classes = {"/output/v/token": S}
    check_declarations(document, classes)
    assert class_for(classes, "/output/v/token") is S
    assert class_for({"/output/v": S, "/output/v/token": INT}, "/output/v/token") is S


def test_r3_c3_11_a_boolean_true_property_keeps_its_ancestor_class() -> None:
    document = _output({"p": {"type": "object", "properties": {"x": True}}})
    check_declarations(document, {"/output/p": S, "/output/p/x": INT})
    assert class_for({"/output/p": S}, "/output/p/x") is S
    assert class_for({"/output/p": S, "/output/p/x": INT}, "/output/p/x") is S


def test_r3_c3_12_a_long_ref_chain_keeps_its_declaration() -> None:
    defs: dict[str, Any] = {f"A{i}": {"$ref": f"#/$defs/A{i + 1}"} for i in range(40)}
    defs["A40"] = PERSON
    document = _output({"x": {"$ref": "#/$defs/A0"}}, **{"$defs": defs})
    classes = {"/output/x/token": S}
    check_declarations(document, classes)
    assert class_for(classes, "/output/x/token") is S


# -- pydantic output inside the subset -----------------------------------------------------
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
    enums, recursion and constrained scalars. Every leaf path is admissible."""
    document = {"output": _Everything.model_json_schema()}
    assert unsupported_construct(document["output"]) is None
    leaves = leaf_instance_paths(document)
    print(f"pydantic leaf paths: {len(leaves)}")
    for path in ("/output/maybe/token", "/output/pet/leaves/items/token", "/output/by_name"):
        assert path in leaves, path
    check_declarations(document, dict.fromkeys(leaves, INT))
    assert unmarked_counts(document, dict.fromkeys(leaves, INT)) == {"input": None, "output": 0}


# -- stored record kinds -------------------------------------------------------------------
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
