"""Contract schemas (JSON Schema 2020-12) shipped as package resources."""

from __future__ import annotations

import json
from datetime import datetime
from functools import cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

FORMAT_CHECKER = FormatChecker()


def parse_timestamp(value: str) -> datetime:
    """RFC 3339 date-time with an explicit offset; the one parser every check shares."""
    if "T" not in value.upper():
        raise ValueError("date-time needs a time part")
    parsed = datetime.fromisoformat(value.replace("z", "Z").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("date-time needs an offset")
    return parsed


@FORMAT_CHECKER.checks("date-time", raises=ValueError)
def _date_time(value: object) -> bool:
    if isinstance(value, str):
        parse_timestamp(value)
    return True


SCHEMAS: tuple[str, ...] = (
    "plan",
    "task",
    "features",
    "handoff",
    "review",
    "progress-entry",
    "gate-evidence",
)


@cache
def load_schema(name: str) -> dict[str, Any]:
    if name not in SCHEMAS:
        raise KeyError(f"unknown contract schema: {name}")
    text = resources.files("e_agent_harness.schemas").joinpath(f"{name}.schema.json").read_text()
    schema: dict[str, Any] = json.loads(text)
    Draft202012Validator.check_schema(schema)
    return schema


def validate(name: str, document: Any) -> list[str]:
    """Return ``<json path>: <message>`` for every violation; empty means valid."""
    validator = Draft202012Validator(load_schema(name), format_checker=FORMAT_CHECKER)
    problems = []
    for error in sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in error.absolute_path) or "<root>"
        problems.append(f"{where}: {error.message}")
    return problems
