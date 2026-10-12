"""Contract schemas (JSON Schema 2020-12) shipped as package resources."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

SCHEMAS: tuple[str, ...] = ("plan", "task", "features", "handoff", "review", "progress-entry")


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
    validator = Draft202012Validator(load_schema(name))
    problems = []
    for error in sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in error.absolute_path) or "<root>"
        problems.append(f"{where}: {error.message}")
    return problems
