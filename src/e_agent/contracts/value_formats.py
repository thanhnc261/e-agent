"""Host-side answer value formats (ADR 0023 §7, owner decision D17).

``CapabilityDescriptor.answer_value_formats`` maps an instance path of an answer's input
(the same RFC 6901 paths as ``data_classes``, ADR 0030) to a format of a closed set. The
host carries a value of a verified answer into a later turn only when its path declares a
format and the value passes it (the carrier, Task 4d.2). The formats sit beside the
schemas, never inside them, so the model-facing tool schemas do not change.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable, Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from . import data_classes as dc
from .common import Record, format_decimal

if TYPE_CHECKING:
    from .capability import CapabilityDescriptor


class FormatKind(StrEnum):
    DECIMAL = "decimal"
    INTEGER = "integer"
    DATE = "date"
    DATE_TIME = "date-time"
    ENUM = "enum"
    REF = "ref"


class ValueFormat(Record):
    """One parsed format; ``values`` lists an ``enum`` format's values, in order."""

    kind: FormatKind
    values: tuple[str, ...] = ()


ENUM_PREFIX = "enum:"
REF_MAX_LENGTH = 256
_PLAIN = {k.value: k for k in FormatKind if k is not FormatKind.ENUM}
_SCHEMA_TYPES = {FormatKind.DECIMAL: {"string", "number"}, FormatKind.INTEGER: {"integer"}}
"""The JSON schema types a format can hold; every other format needs a string."""
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_DATE_TIME = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})"
)


def parse_format(text: str) -> ValueFormat:
    """The format ``text`` names; ``ValueError`` for anything outside the closed set,
    an ``enum`` with an empty or repeated value included."""
    if not isinstance(text, str):
        raise ValueError(f"an answer value format is a string: {text!r}")
    if text in _PLAIN:
        return ValueFormat(kind=_PLAIN[text])
    if text.startswith(ENUM_PREFIX):
        values = tuple(text[len(ENUM_PREFIX) :].split("|"))
        if all(values) and len(set(values)) == len(values):
            return ValueFormat(kind=FormatKind.ENUM, values=values)
        raise ValueError(f"an enum value format has an empty or repeated value: {text!r}")
    raise ValueError(f"unknown answer value format: {text!r}")


def value_passes(fmt: ValueFormat, value: Any, *, nullable: bool) -> bool:
    """Whether ``value`` is a value of ``fmt``. A ``None`` passes only when ``nullable``
    (the schema property admits ``null``). The recorded-source-ref check of a ``ref`` is
    the carrier's, which holds the run's evidence."""
    if value is None:
        return nullable
    if isinstance(value, bool):
        return False
    kind = fmt.kind
    if kind is FormatKind.DECIMAL:
        if isinstance(value, int):
            return True
        if isinstance(value, float):
            return math.isfinite(value)
        return isinstance(value, str) and _canonical_decimal(value)
    if kind is FormatKind.INTEGER:
        return isinstance(value, int)
    if not isinstance(value, str):
        return False
    if kind is FormatKind.ENUM:
        return value in fmt.values
    if kind is FormatKind.REF:
        return 0 < len(value) <= REF_MAX_LENGTH and not any(map(_blank_or_control, value))
    if kind is FormatKind.DATE:
        return _DATE.fullmatch(value) is not None and _parses(date.fromisoformat, value)
    text = value.upper()  # RFC 3339 allows a lower-case "t" and "z"
    return _DATE_TIME.fullmatch(text) is not None and _parses(datetime.fromisoformat, text)


def _canonical_decimal(text: str) -> bool:
    try:
        return format_decimal(Decimal(text)) == text
    except (InvalidOperation, ValueError):
        return False


def _blank_or_control(char: str) -> bool:
    return char.isspace() or unicodedata.category(char) == "Cc"


def _parses(parse: Callable[[str], object], text: str) -> bool:
    try:
        parse(text)
    except ValueError:
        return False
    return True


def check_format_declarations(document: Mapping[str, Any], cap: CapabilityDescriptor) -> None:
    """Admission: ``ValueError`` for an unknown format, a path the input schema does not
    have, a format the schema type there cannot hold (a nullable union judged by its
    non-null member), or a path no ``data_classes`` entry covers, on the path itself or
    an ancestor (``ClassIndex.declared``). The message names the path, never a value."""
    formats = cap.answer_value_formats
    if not formats:
        return
    unsupported = dc.unsupported_sides(document)
    classes = dc.ClassIndex(cap.data_classes)
    for key in sorted(formats):
        prefix = f"answer value format on {key!r}:"
        try:
            fmt = parse_format(formats[key])
        except ValueError as exc:
            raise ValueError(f"{prefix} {exc}") from None
        tokens = dc.parse_pointer(dc.check_class_key(key))
        schema = document.get("input")
        if tokens[0] != "input" or not isinstance(schema, Mapping) or "input" in unsupported:
            raise ValueError(f"{prefix} the path is not in a supported input schema")
        nodes = dc.schema_nodes(schema, tokens[1:])
        if not nodes:
            raise ValueError(f"{prefix} the path resolves to nothing in the input schema")
        found = {t for node in nodes for t in _types(node.get("type"))} - {"null"}
        if not found or not found <= _SCHEMA_TYPES.get(fmt.kind, {"string"}):
            raise ValueError(f"{prefix} a schema of type {sorted(found)} cannot hold it")
        if classes.declared(tokens) is None:
            raise ValueError(f"{prefix} no data_classes entry covers the path or an ancestor")


def _types(declared: Any) -> tuple[str, ...]:
    if isinstance(declared, str):
        return (declared,)
    return tuple(t for t in declared if isinstance(t, str)) if isinstance(declared, list) else ()
