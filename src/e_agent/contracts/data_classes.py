"""Data classes for capability fields and stored records (ADR 0030, target §13.3).

Field classes are pack data declared beside the schema, never inside it:
``CapabilityDescriptor.data_classes`` maps an *instance path* to a ``DataClass``. An
instance path says where a value sits in the capability's input or output data: an
RFC 6901 pointer under ``/input`` or ``/output`` whose tokens are property names, with
``items`` standing for every array index (``/output/orders/items/partner_name``).

A value's class is the most restrictive class declared on its path or on any ancestor
path; an undeclared value is ``personal``, the conservative default. Lookup is string
work over the declared paths and never walks a schema, so no schema alias can lower a
class (owner decision 2026-10-19, Task 3b.3). Keys of a dict-valued property are data,
not paths: a dict and everything in it are classed by a declaration on the dict property
itself, through the ancestor rule.

Schemas serve admission and readiness only: admission refuses a path that resolves to
no property through any branch of the schema, and readiness counts the leaf paths no
declaration covers. Neither decides a class, so an incomplete walk can only refuse.

The stored record kinds of the run ledger are declared once here, store-neutrally, with
a record class and a retention class. A conformance test compares them with what each
store keeps (``tests/conformance/test_record_classes.py``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from enum import StrEnum
from types import MappingProxyType
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


# -- instance paths ---------------------------------------------------------------------
ITEMS = "items"
"""The path token that stands for every array index."""
_BAD_ESCAPE = re.compile(r"~(?![01])")
_INDEX = re.compile(r"0|[1-9][0-9]*")
_NUMERIC = re.compile(r"[+-]?[0-9]+")
_INDEXED = ("prefixItems", "anyOf", "oneOf", "allOf")
_SINGLE = ("items", "additionalProperties")
RESTRICTIVENESS = (
    DataClass.PUBLIC,
    DataClass.INTERNAL,
    DataClass.PERSONAL,
    DataClass.SENSITIVE_PERSONAL,
    DataClass.SECRET,
)
"""Classes from least to most restrictive."""
_DEF_REF = re.compile(r"#/\$defs/([^/~%]+)")
"""The one supported ``$ref`` form: a whole definition of the same schema's root. No
``%``: a percent-encoded name would name a definition other than the literal key."""
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

Path = tuple[str, ...]


def parse_pointer(pointer: str) -> Path:
    """The reference tokens of an RFC 6901 pointer (``~1`` is ``/``, ``~0`` is ``~``).
    A ``~`` followed by anything else is malformed and refused."""
    if not pointer.startswith("/"):
        raise ValueError(f"a JSON pointer starts with '/': {pointer!r}")
    if _BAD_ESCAPE.search(pointer):
        raise ValueError(f"malformed '~' escape in JSON pointer: {pointer!r}")
    return tuple(t.replace("~1", "/").replace("~0", "~") for t in pointer[1:].split("/"))


def format_pointer(tokens: Sequence[str]) -> str:
    return "".join("/" + t.replace("~", "~0").replace("/", "~1") for t in tokens)


def check_class_key(key: str) -> str:
    """A declaration key: an instance path under ``/input`` or ``/output`` with at least
    one property token, no empty token, and ``items`` (never a number) for an index."""
    tokens = parse_pointer(key)
    if len(tokens) < 2 or tokens[0] not in SCHEMA_ROOTS:
        raise ValueError(f"a data class key is an instance path under /input or /output: {key!r}")
    if any(not t for t in tokens):
        raise ValueError(f"a data class key has an empty token: {key!r}")
    if any(_NUMERIC.fullmatch(t) for t in tokens):
        raise ValueError(f"a data class key writes array indices as 'items': {key!r}")
    return key


def instance_token(token: str) -> str:
    """One path token as a class key writes it: a canonical array index is ``items``."""
    return ITEMS if _INDEX.fullmatch(token) else token


def instance_tokens(path: str) -> Path:
    """The tokens of a value's path, every array index written as ``items``."""
    return tuple(instance_token(t) for t in parse_pointer(path))


def most_restrictive(classes: Iterable[DataClass]) -> DataClass | None:
    ranked = [RESTRICTIVENESS.index(c) for c in classes]
    return RESTRICTIVENESS[max(ranked)] if ranked else None


class ClassIndex:
    """One capability's declarations, parsed once, for walking a value's tokens (the
    context assembler classes every value of an observation through it, Task 3d.2)."""

    def __init__(self, classes: Mapping[str, DataClass]) -> None:
        self._by_tokens = {parse_pointer(key): DataClass(c) for key, c in classes.items()}
        self._inner = frozenset(
            tokens[:end] for tokens in self._by_tokens for end in range(1, len(tokens))
        )

    def declared(self, tokens: Path) -> DataClass | None:
        """The most restrictive class declared on ``tokens`` or an ancestor, or None."""
        by_tokens = self._by_tokens
        return most_restrictive(
            by_tokens[tokens[:end]]
            for end in range(1, len(tokens) + 1)
            if tokens[:end] in by_tokens
        )

    def declared_below(self, tokens: Path) -> bool:
        """Whether a declaration names a path strictly below ``tokens``: the value there is
        then schema-shaped (admission resolved that path through the schema), so its keys
        are property names, not data."""
        return tokens in self._inner

    def named(self, tokens: Path) -> bool:
        """Whether a declaration names ``tokens``, a path below it or an ancestor. A key
        whose path no declaration names may be data, not a property name (review D3-12)."""
        return tokens in self._inner or self.declared(tokens) is not None


def declared_class(classes: Mapping[str, DataClass], path: str) -> DataClass | None:
    """The most restrictive class declared on ``path`` or an ancestor path, or None.
    ``ValueError`` for a malformed path."""
    return ClassIndex(classes).declared(instance_tokens(path))


def frozen_classes(classes: Mapping[str, DataClass]) -> Mapping[str, DataClass]:
    """A validated, immutable copy taken at admission (review C3-14): a later change to
    the plugin's own mapping never reaches lookup."""
    return MappingProxyType({check_class_key(k): DataClass(v) for k, v in dict(classes).items()})


def class_for(classes: Mapping[str, DataClass], path: str) -> DataClass:
    """The class of the value at ``path``; ``personal`` when no declaration covers it."""
    found = declared_class(classes, path)
    return UNMARKED_CLASS if found is None else found


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


def unsupported_sides(document: Mapping[str, Any]) -> dict[str, str]:
    """The sides whose schema leaves the supported subset, with the construct."""
    return {
        side: found
        for side in SCHEMA_ROOTS
        if side in document and (found := unsupported_construct(document[side])) is not None
    }


# -- schema walks for admission and readiness (never for a class) -----------------------
def _expand(node: Any, root: Mapping[str, Any], seen: set[int]) -> Iterator[Mapping[str, Any]]:
    """``node`` and every schema it stands for at the same instance path: whole-definition
    ``$ref`` targets and ``anyOf``/``oneOf``/``allOf`` branches, each once."""
    if not isinstance(node, Mapping) or id(node) in seen:
        return
    seen.add(id(node))
    yield node
    ref = node.get("$ref")
    match = _DEF_REF.fullmatch(ref) if isinstance(ref, str) else None
    defs = root.get("$defs")
    if match is not None and isinstance(defs, Mapping):
        yield from _expand(defs.get(match.group(1)), root, seen)
    for keyword in ("anyOf", "oneOf", "allOf"):
        branches = node.get(keyword)
        for branch in branches if isinstance(branches, list) else ():
            yield from _expand(branch, root, seen)


def _children(node: Mapping[str, Any], token: str) -> Iterator[tuple[Any, bool]]:
    """The schemas one path token leads to from ``node``, each with whether it is a
    property (as opposed to an array element)."""
    properties = node.get("properties")
    if isinstance(properties, Mapping) and token in properties:
        yield properties[token], True
    if token == ITEMS:
        if isinstance(node.get("items"), Mapping):
            yield node["items"], False
        prefix = node.get("prefixItems")
        for element in prefix if isinstance(prefix, list) else ():
            yield element, False


def path_exists(schema: Mapping[str, Any], tokens: Sequence[str]) -> bool:
    """Whether the instance path ``tokens`` (below the side) resolves to a property
    through at least one branch of ``schema``."""
    frontier: list[tuple[Any, bool]] = [(schema, False)]
    for token in tokens:
        frontier = [
            child
            for node, _ in frontier
            for expanded in _expand(node, schema, set())
            for child in _children(expanded, token)
        ]
        if not frontier:
            return False
    return any(is_property for _, is_property in frontier)


def check_declarations(document: Mapping[str, Any], classes: Mapping[str, DataClass]) -> None:
    """Admission: ``ValueError`` for a declaration on a side outside the supported subset
    or a path that resolves to no property. The message names the side, the construct or
    the path, never a value."""
    unsupported = unsupported_sides(document)
    for key in sorted(classes):
        tokens = parse_pointer(check_class_key(key))
        side = tokens[0]
        if side in unsupported:
            raise ValueError(
                f"declares data classes on its {side} schema, which uses "
                f"{unsupported[side]}; that is outside the supported subset"
            )
        schema = document.get(side)
        if not isinstance(schema, Mapping) or not path_exists(schema, tokens[1:]):
            raise ValueError(f"{key!r} resolves to no property of its {side} schema")


def _collect(
    node: Any, root: Mapping[str, Any], path: Path, out: dict[Path, None], stack: frozenset[int]
) -> None:
    for expanded in _expand(node, root, set()):
        if id(expanded) in stack:  # a recursive schema: stop rather than loop
            continue
        below = stack | {id(expanded)}
        properties = expanded.get("properties")
        for name, child in properties.items() if isinstance(properties, Mapping) else ():
            out[(*path, str(name))] = None
            _collect(child, root, (*path, str(name)), out, below)
        prefix = expanded.get("prefixItems")
        elements = [expanded.get("items"), *(prefix if isinstance(prefix, list) else ())]
        for element in elements:
            if isinstance(element, Mapping):
                _collect(element, root, (*path, ITEMS), out, below)


def leaf_instance_paths(document: Mapping[str, Any]) -> tuple[str, ...]:
    """Every property path of the schemas with no property path below it, in schema
    order. A dict-valued property is a leaf: its keys are data."""
    leaves: list[str] = []
    for side in SCHEMA_ROOTS:
        if not isinstance(schema := document.get(side), Mapping):
            continue
        found: dict[Path, None] = {}
        _collect(schema, schema, (side,), found, frozenset())
        inner = {p[:end] for p in found for end in range(1, len(p))}
        leaves.extend(format_pointer(p) for p in found if p not in inner)
    return tuple(leaves)


def unmarked_counts(
    document: Mapping[str, Any], classes: Mapping[str, DataClass]
) -> dict[str, int | None]:
    """Leaf paths no declaration covers, per side; None for a side with no schema or an
    unsupported one, so readiness tells "fully classed" from "unknown". Informational."""
    unsupported = unsupported_sides(document)
    unmarked = [p for p in leaf_instance_paths(document) if declared_class(classes, p) is None]
    return {
        side: None
        if side not in document or side in unsupported
        else sum(p.startswith(f"/{side}/") for p in unmarked)
        for side in SCHEMA_ROOTS
    }
