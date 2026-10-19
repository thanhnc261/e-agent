"""Grounding records (ADR 0033): a citation that ties a claim to this run's evidence.

A `Citation` is model output, a claim the kernel checks: it names an observation of the run
by ``evidence_id``, an RFC 6901 ``pointer`` into that observation's ``data``, and the
``value`` the model says is there. It travels in the kernel envelope beside a proposal's
arguments (`ActionProposal.citations`), never inside them, so a domain answer model is
unchanged. It never grants approval, changes policy or marks anything verified (PR-13).

The record accepts any pointer text: a pointer that is not RFC 6901, or that names nothing,
is an unresolved citation the kernel returns as a repair, never a refused proposal. The
value must be a JSON value, so the kernel can always digest it (ADR 0006). At rest a
citation is its evidence id, pointer and value digest, never the value (PR-26).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from pydantic import field_validator

from .common import Record


def _check_json(value: Any, depth: int = 0) -> None:
    if depth > 64:
        raise ValueError("a cited value nests too deeply")
    if value is None or isinstance(value, bool | str | int):
        return
    if isinstance(value, float | Decimal):
        if not math.isfinite(value):
            raise ValueError("a cited number must be finite")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("a cited object has string keys")
            _check_json(item, depth + 1)
        return
    if isinstance(value, list | tuple):
        for item in value:
            _check_json(item, depth + 1)
        return
    raise ValueError(f"a cited value is a JSON value, not {type(value).__name__}")


class Citation(Record):
    """One claim that ``value`` is at ``pointer`` in the data of this run's observation
    ``evidence_id`` (ADR 0033 §1)."""

    evidence_id: str
    pointer: str
    """An RFC 6901 JSON pointer into the observation's ``data``; ``""`` is the whole data."""
    value: Any
    """The value the model claims is there; compared under ``jcs-sha256-v1``, never stored."""

    @field_validator("value")
    @classmethod
    def _json_value(cls, value: Any) -> Any:
        _check_json(value)
        return value
