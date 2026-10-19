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

from collections.abc import Iterator, Mapping, Sequence
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


def parse_pointer(pointer: str) -> tuple[str, ...]:
    """The reference tokens of an RFC 6901 pointer (``~1`` is ``/``, ``~0`` is ``~``)."""
    if not pointer.startswith("/"):
        raise ValueError(f"a JSON pointer starts with '/': {pointer!r}")
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


def _deref(node: Any, root: Mapping[str, Any]) -> Any:
    """Follow local ``$ref`` (``#/...``) against ``root``; None for any other reference."""
    for _ in range(_MAX_REFS):
        if not isinstance(node, Mapping) or "$ref" not in node:
            return node
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#"):
            return None
        node = _step_all(root, parse_pointer(ref[1:]) if ref != "#" else (), root, deref=False)
    return None


def _step(node: Any, token: str) -> Any:
    if isinstance(node, Mapping):
        return node.get(token)
    if isinstance(node, list) and token.isdigit() and int(token) < len(node):
        return node[int(token)]
    return None


def _step_all(node: Any, tokens: Sequence[str], root: Mapping[str, Any], *, deref: bool) -> Any:
    for token in tokens:
        found = _step(node, token)
        if found is None and deref:
            found = _step(_deref(node, root), token)
        if found is None:
            return None
        node = found
    return node


def schema_document(
    input_schema: Mapping[str, Any] | None, output_schema: Mapping[str, Any] | None
) -> dict[str, Mapping[str, Any]]:
    """``{"input": ..., "output": ...}`` holding the schemas that exist."""
    document = {"input": input_schema, "output": output_schema}
    return {name: schema for name, schema in document.items() if schema is not None}


def resolve_property(document: Mapping[str, Any], pointer: str) -> Mapping[str, Any] | None:
    """The property schema ``pointer`` names in ``document``, or None when it names none."""
    try:
        tokens = _class_pointer_tokens(pointer)
    except ValueError:
        return None
    root = document.get(tokens[0])
    if not isinstance(root, Mapping):
        return None
    found = _step_all(root, tokens[1:], root, deref=True)
    return found if isinstance(found, Mapping) else None


def _walk(
    node: Any, root: Mapping[str, Any], path: tuple[str, ...], refs: frozenset[str]
) -> Iterator[tuple[tuple[str, ...], bool]]:
    """Yield ``(pointer tokens, is_leaf)`` for every property schema below ``node``."""
    if isinstance(node, Mapping) and isinstance(node.get("$ref"), str):
        ref = node["$ref"]
        if ref in refs:  # a recursive schema: stop rather than loop
            return
        refs, node = refs | {ref}, _deref(node, root)
    if not isinstance(node, Mapping):
        return
    properties = node.get("properties")
    if isinstance(properties, Mapping):
        for name, child in properties.items():
            here = (*path, "properties", str(name))
            below = list(_walk(child, root, here, refs))
            yield here, not below
            yield from below
    items = node.get("items")
    if isinstance(items, Mapping):
        yield from _walk(items, root, (*path, "items"), refs)
    for key in ("prefixItems", "anyOf", "oneOf", "allOf"):
        branches = node.get(key)
        if isinstance(branches, list):
            for i, branch in enumerate(branches):
                yield from _walk(branch, root, (*path, key, str(i)), refs)


def leaf_property_pointers(document: Mapping[str, Any]) -> tuple[str, ...]:
    """Every property schema with no property below it, as a pointer, in schema order."""
    leaves: list[str] = []
    for name in SCHEMA_ROOTS:
        root = document.get(name)
        if isinstance(root, Mapping):
            leaves.extend(
                format_pointer(tokens)
                for tokens, leaf in _walk(root, root, (name,), frozenset())
                if leaf
            )
    return tuple(leaves)


def declared_class(classes: Mapping[str, DataClass], pointer: str) -> DataClass | None:
    """The class declared on ``pointer`` or its nearest classed ancestor, else None."""
    by_tokens = {parse_pointer(p): c for p, c in classes.items()}
    tokens = parse_pointer(pointer)
    for end in range(len(tokens), 0, -1):
        found = by_tokens.get(tokens[:end])
        if found is not None:
            return found
    return None


def class_of(classes: Mapping[str, DataClass], pointer: str) -> DataClass:
    """The class of the property ``pointer`` names; ``personal`` when unmarked."""
    found = declared_class(classes, pointer)
    return UNMARKED_CLASS if found is None else found


def unmarked_pointers(
    document: Mapping[str, Any], classes: Mapping[str, DataClass]
) -> tuple[str, ...]:
    """The leaf properties of ``document`` that no declaration covers."""
    return tuple(p for p in leaf_property_pointers(document) if declared_class(classes, p) is None)
