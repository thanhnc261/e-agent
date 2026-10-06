"""Approval digest: RFC 8785 (JCS) serialization of a number-free profile (ADR 0006).

Allowed JSON types are objects (string keys), arrays, strings, booleans and null.
JSON numbers are forbidden: amounts, quantities and integers travel as canonical
strings, so JCS's IEEE-754 number serialization never applies.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

DIGEST_PROFILE = "jcs-sha256-v1"


class CanonicalizationError(ValueError):
    """The value is outside the digest profile."""


def _encode_string(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:  # lone surrogates are not valid I-JSON
        raise CanonicalizationError("strings must be valid Unicode") from exc
    # json.dumps(ensure_ascii=False) escapes exactly what RFC 8785 §3.2.2.2 requires:
    # quote, backslash, \b \t \n \f \r and other C0 controls as lowercase \u00xx.
    return json.dumps(value, ensure_ascii=False)


def _utf16_key(key: str) -> bytes:
    return key.encode("utf-16-be")


def _canonicalize(value: Any, path: str) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _encode_string(value)
    if isinstance(value, int | float):
        raise CanonicalizationError(f"JSON numbers are not allowed in the profile at {path}")
    if isinstance(value, Mapping):
        items = []
        for key in sorted(value, key=lambda k: _utf16_key(_require_str_key(k, path))):
            items.append(f"{_encode_string(key)}:{_canonicalize(value[key], f'{path}.{key}')}")
        return "{" + ",".join(items) + "}"
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return "[" + ",".join(_canonicalize(v, f"{path}[{i}]") for i, v in enumerate(value)) + "]"
    raise CanonicalizationError(f"unsupported type {type(value).__name__} at {path}")


def _require_str_key(key: object, path: str) -> str:
    if not isinstance(key, str):
        raise CanonicalizationError(f"object keys must be strings at {path}")
    return key


def canonicalize(value: Any) -> str:
    """Return the canonical JCS text of ``value`` under the digest profile."""
    return _canonicalize(value, "$")


def digest(value: Any) -> str:
    """Return ``jcs-sha256-v1:<hex>`` for ``value``."""
    canonical = canonicalize(value).encode("utf-8")
    return f"{DIGEST_PROFILE}:{hashlib.sha256(canonical).hexdigest()}"
