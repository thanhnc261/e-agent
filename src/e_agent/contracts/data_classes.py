"""Data classes for capability fields and stored records (ADR 0030, target §13.3).

Field classes are pack data declared beside the schema, never inside it:
``CapabilityDescriptor.data_classes`` maps an RFC 6901 pointer into the document
``{"input": <input schema>, "output": <output schema>}`` to a ``DataClass``. A pointer
names a property schema; an ``items`` step matches every array index, and a local
``$ref`` is followed against the schema it appears in. A class applies to the property
and to every property below it that has no class of its own. An unmarked property counts
as ``personal``, the conservative default.

The stored record kinds of the run ledger are declared once here, store-neutrally, with
a record class and a retention class. A conformance test compares them with what each
store keeps (``tests/conformance/test_record_classes.py``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from enum import StrEnum
from typing import Any

from .common import Record


class DataClass(StrEnum):
    """What a field's values are, which decides where they may go (target §13.3)."""

    PUBLIC = "public"
    """Published or non-business data."""
    INTERNAL = "internal"
    """Business data without personal data."""
    PERSONAL = "personal"
    """Identifies or describes a person (contact, employee, partner person)."""
    SENSITIVE_PERSONAL = "sensitive_personal"
    """Special-category personal data."""
    SECRET = "secret"  # noqa: S105 - a data class name, not a credential
    """Credentials and keys: never in the ledger, the context or an export."""


UNMARKED_CLASS = DataClass.PERSONAL
"""The class of a property no declaration covers (ADR 0030)."""

SCHEMA_ROOTS = ("input", "output")
"""The two schemas a capability's class pointers start from."""


class RecordClass(StrEnum):
    """What a stored record kind holds (ADR 0030, target §13.3)."""

    AUDIT_SKELETON = "audit_skeleton"
    """Ids, digests, actors, states, reason codes and timestamps: the audit record. A
    row's payload columns may expire (Phase 7); the row itself is kept."""
    BUSINESS_PAYLOAD = "business_payload"
    """Arguments, observations, outcomes, model text and continuations."""
    INFRA = "infra"
    """Work queue, leases and idempotency rows."""


class RetentionClass(StrEnum):
    """How long a stored record kind is kept. The periods are profile settings and the
    purge job is Phase 7 (ADR 0030); this names the class each kind belongs to."""

    AUDIT = "audit"
    """Kept for the tenant's audit period; the purge job never deletes the row."""
    PAYLOAD = "payload"
    """Expires after the profile's payload retention period."""
    OPERATIONAL = "operational"
    """Kept while the run needs it for correctness (claims, deduplication); removed with
    its run, never read as business data."""


class RecordKind(Record):
    """One kind of record a run store keeps."""

    kind: str
    record_class: RecordClass
    retention: RetentionClass
    holds: str
    """What one record of this kind holds, in a phrase."""


def _kinds(*kinds: RecordKind) -> Mapping[str, RecordKind]:
    return {k.kind: k for k in kinds}


_AUDIT = {"record_class": RecordClass.AUDIT_SKELETON, "retention": RetentionClass.AUDIT}
_PAYLOAD = {"record_class": RecordClass.BUSINESS_PAYLOAD, "retention": RetentionClass.PAYLOAD}
_INFRA = {"record_class": RecordClass.INFRA, "retention": RetentionClass.OPERATIONAL}

RECORD_KINDS: Mapping[str, RecordKind] = _kinds(
    RecordKind(kind="runs", holds="a run's state, requester and revision", **_AUDIT),
    RecordKind(kind="run_events", holds="the run's append-only event ledger", **_AUDIT),
    RecordKind(kind="actions", holds="an action's state, digest and binding", **_AUDIT),
    RecordKind(kind="approvals", holds="an approval decision and its digest", **_AUDIT),
    RecordKind(kind="receipts", holds="an execution attempt's receipt", **_AUDIT),
    RecordKind(kind="run_steps", holds="a step of a run and its status", **_AUDIT),
    RecordKind(kind="outcome_reports", holds="a verification outcome", **_PAYLOAD),
    RecordKind(kind="continuations", holds="the driver's resume state", **_PAYLOAD),
    RecordKind(kind="action_plans", holds="a proposed plan with its arguments", **_PAYLOAD),
    RecordKind(kind="operation_reservations", holds="a write's logical operation claim", **_INFRA),
    RecordKind(kind="api_idempotency", holds="an API idempotency key", **_INFRA),
    RecordKind(kind="run_work", holds="a queued host command and its lease", **_INFRA),
)
"""Every record kind the run stores keep, by name (both stores inherit it, ENG-STORE-1)."""


def record_kind(kind: str) -> RecordKind:
    """The declaration of a stored record kind; ``KeyError`` when there is none."""
    return RECORD_KINDS[kind]


# -- pointers into {"input": <schema>, "output": <schema>} --------------------------------
_MAX_REFS = 32
_BAD_ESCAPE = re.compile(r"~(?![01])")
_INDEX = re.compile(r"0|[1-9][0-9]*")
_NAMED = frozenset({"properties", "$defs"})
"""Keywords whose value maps a name to a schema (``$defs`` only at a schema root)."""
_INDEXED = ("prefixItems", "anyOf", "oneOf", "allOf")
"""Keywords whose value is a list of schemas."""
_SINGLE = ("items", "additionalProperties")
"""Keywords whose value is one schema."""
RESTRICTIVENESS = (
    DataClass.PUBLIC,
    DataClass.INTERNAL,
    DataClass.PERSONAL,
    DataClass.SENSITIVE_PERSONAL,
    DataClass.SECRET,
)
"""Classes from least to most restrictive."""

_DEF_REF = re.compile(r"#/\$defs/([^/~]+)")
"""The one supported ``$ref`` form: a whole definition of the same schema's root."""
REF_ANNOTATIONS = frozenset(
    {"title", "description", "default", "examples", "deprecated", "readOnly", "writeOnly"}
    | {"$comment"}
)
"""Siblings a ``$ref`` node may carry: annotations, never a schema-bearing keyword."""
_NON_SCHEMA = REF_ANNOTATIONS | {
    "type",
    "required",
    "enum",
    "const",
    "format",
    "pattern",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minProperties",
    "maxProperties",
    "discriminator",
}
"""Keywords whose values are data or assertions, never schemas (``x-`` extensions too)."""

Location = tuple[str, ...]
"""Where a schema sits in the document, ``$ref`` hops resolved: its identity."""


def parse_pointer(pointer: str) -> tuple[str, ...]:
    """The reference tokens of an RFC 6901 pointer (``~1`` is ``/``, ``~0`` is ``~``).
    A ``~`` followed by anything else is malformed and refused."""
    if not pointer.startswith("/"):
        raise ValueError(f"a JSON pointer starts with '/': {pointer!r}")
    if _BAD_ESCAPE.search(pointer):
        raise ValueError(f"malformed '~' escape in JSON pointer: {pointer!r}")
    return tuple(t.replace("~1", "/").replace("~0", "~") for t in pointer[1:].split("/"))


def format_pointer(tokens: Sequence[str]) -> str:
    return "".join("/" + t.replace("~", "~0").replace("/", "~1") for t in tokens)


def _class_pointer_tokens(pointer: str) -> tuple[str, ...]:
    tokens = parse_pointer(pointer)
    if len(tokens) < 3 or tokens[0] not in SCHEMA_ROOTS or tokens[-2] != "properties":
        raise ValueError(
            f"a data class pointer names a property under /input or /output: {pointer!r}"
        )
    return tokens


def check_class_pointer(pointer: str) -> str:
    """Syntax only: a pointer into one of the two schemas that ends at a property name.
    Whether it resolves needs the schemas; the registry checks that at admission."""
    _class_pointer_tokens(pointer)
    return pointer


def schema_document(
    input_schema: Mapping[str, Any] | None, output_schema: Mapping[str, Any] | None
) -> dict[str, Mapping[str, Any]]:
    """``{"input": ..., "output": ...}`` holding the schemas that exist."""
    document = {"input": input_schema, "output": output_schema}
    return {name: schema for name, schema in document.items() if schema is not None}


# -- the supported schema subset ------------------------------------------------------------
def _unsupported_in(node: Any, defs: Mapping[str, Any], *, root: bool = False) -> str | None:
    """The first construct of ``node`` outside the supported subset, by keyword, or None."""
    if isinstance(node, bool):
        return None
    if not isinstance(node, Mapping):
        return "a schema that is not an object"
    if "$ref" in node:
        ref = node["$ref"]
        match = _DEF_REF.fullmatch(ref) if isinstance(ref, str) else None
        if match is None or match.group(1) not in defs:
            return "a $ref to anything but a whole #/$defs/<Name> definition"
        extra = sorted(k for k in node if k != "$ref" and not _annotation(k, REF_ANNOTATIONS))
        return f"a $ref beside the keyword {extra[0]!r}" if extra else None
    for key, value in node.items():
        if key == "$defs" and root and isinstance(value, Mapping):
            continue  # each definition is checked by unsupported_construct
        if key == "properties" and isinstance(value, Mapping):
            children: list[Any] = list(value.values())
        elif key in _SINGLE:
            children = [value]
        elif key in _INDEXED and isinstance(value, list):
            children = value
        elif _annotation(key, _NON_SCHEMA):
            continue
        else:
            return f"the keyword {key!r}"
        for child in children:
            if (found := _unsupported_in(child, defs)) is not None:
                return found
    return None


def _annotation(key: str, allowed: frozenset[str]) -> bool:
    return key in allowed or key.startswith("x-")


def unsupported_construct(schema: Mapping[str, Any]) -> str | None:
    """The first construct of a schema outside the subset data classes support, or None.

    Supported: the data keywords in ``_NON_SCHEMA``; ``properties/<name>``, ``items``,
    ``additionalProperties``, ``prefixItems/<i>``, ``anyOf/<i>``, ``oneOf/<i>`` and
    ``allOf/<i>``; ``$defs/<Name>`` at the schema root; and ``$ref`` only as
    ``#/$defs/<Name>`` (a whole definition) with annotation siblings only. Everything
    else (``if``/``then``/``else``, ``patternProperties``, ``not``, ``dependentSchemas``,
    ``unevaluatedProperties``, a ``$ref`` into a definition, ...) is unsupported: a side
    that uses it admits no declaration, and every value on it counts as ``personal``."""
    defs = schema.get("$defs", {})
    if not isinstance(defs, Mapping):
        return "the keyword '$defs'"
    for node in (schema, *defs.values()):
        if (found := _unsupported_in(node, defs, root=node is schema)) is not None:
            return found
    return None


def _ref_target(
    node: Mapping[str, Any], document: Mapping[str, Any], loc: Location
) -> tuple[Mapping[str, Any], Location] | None:
    """The definition a supported ``$ref`` names, in the schema ``loc`` is in."""
    ref = node.get("$ref")
    match = _DEF_REF.fullmatch(ref) if isinstance(ref, str) else None
    defs = document[loc[0]].get("$defs")
    if match is None or not isinstance(defs, Mapping):
        return None
    target = defs.get(match.group(1))
    return (target, (loc[0], "$defs", match.group(1))) if isinstance(target, Mapping) else None


def _child(node: Mapping[str, Any], keyword: str, name: str | None) -> Any:
    value = node.get(keyword)
    if keyword in _SINGLE:
        return value
    if keyword in _NAMED:
        return value.get(name) if isinstance(value, Mapping) and name is not None else None
    if isinstance(value, list) and name is not None and _INDEX.fullmatch(name):
        return value[int(name)] if int(name) < len(value) else None
    return None


def _step(
    node: Mapping[str, Any], loc: Location, keyword: str, name: str | None, document: Any
) -> tuple[Mapping[str, Any], Location] | None:
    """One schema keyword step, through ``$ref`` hops (a supported ``$ref`` has no
    schema-bearing sibling, so a node either holds the keyword or refers on)."""
    for _ in range(_MAX_REFS):
        found = _child(node, keyword, name)
        if isinstance(found, Mapping):
            return found, (*loc, keyword) if name is None else (*loc, keyword, name)
        hop = _ref_target(node, document, loc)
        if hop is None:
            return None
        node, loc = hop
    return None


def _property_locations(document: Mapping[str, Any], pointer: str) -> list[Location] | None:
    """The location of every property schema along ``pointer``, outermost first, or None
    when the pointer leaves schema context (``examples``, ``default`` and other data
    keywords are not schemas) or names nothing."""
    tokens = parse_pointer(pointer)
    if not tokens or tokens[0] not in SCHEMA_ROOTS:
        return None
    root = document.get(tokens[0])
    if not isinstance(root, Mapping):
        return None
    node: Mapping[str, Any] = root
    loc: Location = (tokens[0],)
    found: list[Location] = []
    i = 1
    while i < len(tokens):
        keyword = tokens[i]
        if keyword in _SINGLE:
            name, i = None, i + 1
        elif (keyword in _NAMED or keyword in _INDEXED) and i + 1 < len(tokens):
            name, i = tokens[i + 1], i + 2
        else:
            return None
        step = _step(node, loc, keyword, name, document)
        if step is None:
            return None
        node, loc = step
        if keyword == "properties":
            found.append(loc)
    return found


def resolve_property(document: Mapping[str, Any], pointer: str) -> Location | None:
    """The location of the property schema ``pointer`` names, or None when it names none."""
    try:
        _class_pointer_tokens(pointer)
        found = _property_locations(document, pointer)
    except ValueError:
        return None
    # the pointer ends at ``properties/<name>``, so the last location is the one it names
    return found[-1] if found else None


def _walk(
    node: Any, document: Mapping[str, Any], loc: Location, path: Location, refs: frozenset[str]
) -> Iterator[tuple[Location, bool]]:
    """Yield ``(pointer tokens, is_leaf)`` for every property schema below ``node``,
    through sibling keywords and ``$ref`` alike."""
    if not isinstance(node, Mapping):
        return
    if isinstance(node.get("$ref"), str) and node["$ref"] not in refs:
        hop = _ref_target(node, document, loc)
        if hop is not None:
            yield from _walk(hop[0], document, hop[1], path, refs | {node["$ref"]})
    properties = node.get("properties")
    if isinstance(properties, Mapping):
        for name, child in properties.items():
            here = (*path, "properties", str(name))
            below = list(_walk(child, document, (*loc, "properties", str(name)), here, refs))
            yield here, not below
            yield from below
    for keyword in _SINGLE:
        yield from _walk(node.get(keyword), document, (*loc, keyword), (*path, keyword), refs)
    for keyword in _INDEXED:
        branches = node.get(keyword)
        for i, branch in enumerate(branches if isinstance(branches, list) else ()):
            step = (keyword, str(i))
            yield from _walk(branch, document, (*loc, *step), (*path, *step), refs)


def leaf_property_pointers(document: Mapping[str, Any]) -> tuple[str, ...]:
    """Every property schema with no property below it, as a pointer, in schema order."""
    leaves: list[str] = []
    for name in SCHEMA_ROOTS:
        root = document.get(name)
        walked = _walk(root, document, (name,), (name,), frozenset())
        leaves.extend(dict.fromkeys(format_pointer(t) for t, leaf in walked if leaf))
    return tuple(leaves)


def most_restrictive(classes: Iterable[DataClass]) -> DataClass | None:
    ranked = [RESTRICTIVENESS.index(c) for c in classes]
    return RESTRICTIVENESS[max(ranked)] if ranked else None


class ClassIndex:
    """A capability's classes keyed by the location of the schema each one names, so a
    declaration and a lookup that reach one schema through different ``$ref`` paths
    agree. A value's class is the most restrictive class declared on its property or on
    any property above it: a deeper declaration never lowers a class. A side whose
    schema leaves the supported subset (``unsupported_construct``) admits no declaration
    and classes every value ``personal``."""

    def __init__(self, document: Mapping[str, Any], classes: Mapping[str, DataClass]) -> None:
        """Raises ``ValueError`` for a declaration on an unsupported side, a pointer that
        names no property schema, or two pointers that reach one schema with different
        classes. The message names the side and construct, never a value."""
        self._document = document
        self.unsupported: dict[str, str] = {
            side: found
            for side in SCHEMA_ROOTS
            if side in document and (found := unsupported_construct(document[side]))
        }
        self._by_location: dict[Location, DataClass] = {}
        for pointer, data_class in sorted(classes.items()):
            side = pointer.split("/", 2)[1] if pointer.startswith("/") else ""
            if side in self.unsupported:
                raise ValueError(
                    f"declares data classes on its {side} schema, which uses "
                    f"{self.unsupported[side]}; that is outside the supported subset"
                )
            loc = resolve_property(document, pointer)
            if loc is None:
                raise ValueError(f"{pointer!r} names no property schema")
            if self._by_location.setdefault(loc, data_class) != data_class:
                raise ValueError(f"{pointer!r} reaches a schema already classed differently")

    def declared(self, pointer: str) -> DataClass | None:
        """The class declarations give the value at ``pointer``, or None when none does
        (also when the pointer names nothing, or its side is unsupported)."""
        tokens = parse_pointer(pointer)
        if tokens[0] in self.unsupported:
            return None
        found = _property_locations(self._document, pointer) or []
        return most_restrictive(self._by_location[at] for at in found if at in self._by_location)

    def class_of(self, pointer: str) -> DataClass:
        """The class of the value at ``pointer``; ``personal`` when unmarked. ``ValueError``
        for a malformed pointer."""
        found = self.declared(pointer)
        return UNMARKED_CLASS if found is None else found

    def unmarked(self) -> tuple[str, ...]:
        """The leaf properties of the supported sides that no declaration covers."""
        supported = {k: v for k, v in self._document.items() if k not in self.unsupported}
        return tuple(p for p in leaf_property_pointers(supported) if self.declared(p) is None)

    def unmarked_counts(self) -> dict[str, int | None]:
        """Unmarked leaves per side; None for a side with no schema or an unsupported one
        (``unsupported`` says which), so readiness tells "fully classed" from "unknown"."""
        unmarked = self.unmarked()
        return {
            side: None
            if side not in self._document or side in self.unsupported
            else sum(p.startswith(f"/{side}/") for p in unmarked)
            for side in SCHEMA_ROOTS
        }
