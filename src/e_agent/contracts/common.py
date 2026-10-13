"""Shared primitives: strict base record, decimal strings, UTC timestamps, IDs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer


class Record(BaseModel):
    """Immutable wire record that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=False)


def _canonical_decimal(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("decimal values cross wire boundaries as strings")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"not a decimal string: {value!r}") from exc
    if not number.is_finite():
        raise ValueError("NaN/Infinity are not allowed")
    return format_decimal(number)


def format_decimal(number: Decimal) -> str:
    """Canonical decimal string: no exponent, no trailing zeros, '-0' becomes '0'."""
    if not number.is_finite():
        raise ValueError("NaN/Infinity are not allowed")
    text = format(number.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"-0", ""}:
        text = "0"
    return text


DecimalStr = Annotated[str, AfterValidator(_canonical_decimal)]
"""Decimal quantity or amount carried as a canonical string (never binary float)."""


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware UTC")
    return value.astimezone(UTC)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


UtcDatetime = Annotated[
    datetime, AfterValidator(_require_utc), PlainSerializer(_iso_utc, return_type=str)
]


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    """Opaque internal identifier, e.g. ``run_3f2a…``."""
    if not prefix.isidentifier():
        raise ValueError(f"invalid id prefix: {prefix!r}")
    return f"{prefix}_{uuid.uuid4().hex}"
