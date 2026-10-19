"""What the pydantic-ai driver offers for grounding, and how it reads it back (ADR 0033 §5).

The kernel sets ``DriverInput.grounding`` per call from the run's pinned mode; the driver
never reads the profile (plan D8). With ``off`` nothing here is used, so every tool schema and
instruction is today's, byte for byte (ENG-TOGGLE-1). Otherwise:

- an answer tool's schema gains a sibling ``citations`` array beside the answer arguments,
  and a write tool's and the plan tool's gain ``rationale``. Each schema is a deep copy, so
  the ``off`` schemas the driver also holds never change;
- ``cite_and_answer`` also offers ``grounded_answer_v1``, the generic grounded answer
  ``grounded.answer.v1`` (ADR 0033 §3), which the kernel admitted for the run.

A call's envelope fields leave its arguments before they reach a proposal: ``citations``
becomes `ActionProposal.citations` and ``rationale`` `ActionProposal.rationale` or
`ActionPlan.rationale`. An envelope the records refuse is a fixed refusal returned to the
model as the call's error, never an exception and never model text. The rationale schema
carries the record's id pattern and summary bound, so a model that follows it is not refused
(3e.3 open item). It offers no ``alternatives``: a rejected alternative names a proposal
digest that the model is never shown. Citations and rationale are model claims the kernel
checks; they grant nothing (PR-13).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from e_agent.contracts.grounding import SUMMARY_MAX, Citation, ProposalRationale
from pydantic import ValidationError

from pydantic_ai import ToolDefinition

CITATIONS = "citations"
RATIONALE = "rationale"
GROUNDED_TOOL = "grounded_answer_v1"
"""The generic grounded answer's tool name: ``grounded.answer.v1`` as a tool name."""
GROUNDED_CONNECTION = "kernel"
"""The connection of a generic grounded answer proposal; the kernel ignores it (PR-12)."""
ID_PATTERN = r"^[A-Za-z0-9_.:@#/+-]{1,128}$"
"""The id shape `ProposalRationale` accepts (``RefId``): no whitespace, no prose."""

GROUNDING_INSTRUCTIONS = (
    "Each read result carries an evidence_id. When a tool offers citations, cite each value "
    "your answer relies on: the evidence_id of the read, an RFC 6901 JSON pointer into that "
    "read's data (for example /quantity or /offers/0/unit_price) and the exact value found "
    "there. When a write tool offers a rationale, give the goal (the task as id@version, or "
    "run), the evidence ids and rule ids you relied on, and a one-paragraph summary. The host "
    "checks every citation and reference; they grant no approval or authority."
)
"""Added to the instructions only on a call whose offer is not ``off``."""

CITATION_REFUSAL = (
    "citations is a list of {evidence_id, pointer, value}: the evidence_id of a read, an RFC "
    "6901 JSON pointer into its data and the JSON value found there"
)
RATIONALE_REFUSAL = (
    "rationale is {goal_ref, cited_evidence, rules_considered, summary}: ids without spaces "
    f"and a summary of at most {SUMMARY_MAX} characters"
)
GROUNDED_REFUSAL = (
    "the grounded answer takes a non-empty summary and at least one citation of a value a "
    "read returned"
)
GROUNDING_REFUSALS = frozenset({CITATION_REFUSAL, RATIONALE_REFUSAL, GROUNDED_REFUSAL})
"""The fixed refusals of a grounding envelope, returned to the model as the call's error."""

_ID: dict[str, Any] = {"type": "string", "pattern": ID_PATTERN}
CITATIONS_SCHEMA: dict[str, Any] = {
    "type": "array",
    "description": (
        "Each value this answer relies on: the read's evidence_id, an RFC 6901 JSON pointer "
        "into that read's data, and the exact value there. Checked by the host."
    ),
    "items": {
        "type": "object",
        "properties": {
            "evidence_id": {"type": "string"},
            "pointer": {"type": "string"},
            "value": {},
        },
        "required": ["evidence_id", "pointer", "value"],
        "additionalProperties": False,
    },
}
RATIONALE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "Why this is proposed: shown to the approver as model-authored and checked by the "
        "host; it never changes what is approved."
    ),
    "properties": {
        "goal_ref": {**_ID, "description": "The task as id@version, or run."},
        "cited_evidence": {
            "type": "array",
            "items": {**_ID, "description": "The evidence_id of a read you relied on."},
        },
        "rules_considered": {
            "type": "array",
            "items": {**_ID, "description": "A rule id, as a finding names it."},
        },
        "summary": {"type": "string", "maxLength": SUMMARY_MAX},
    },
    "required": ["goal_ref", "summary"],
    "additionalProperties": False,
}


def with_field(schema: Mapping[str, Any], name: str, field: Mapping[str, Any]) -> dict[str, Any]:
    """A deep copy of an object schema with one more optional property."""
    grounded = copy.deepcopy(dict(schema))
    grounded.setdefault("properties", {})[name] = copy.deepcopy(dict(field))
    return grounded


def grounded_tool() -> ToolDefinition:
    """The generic grounded answer, offered only for ``cite_and_answer`` (ADR 0033 §3)."""
    citations = {**copy.deepcopy(CITATIONS_SCHEMA), "minItems": 1}
    return ToolDefinition(
        name=GROUNDED_TOOL,
        description=(
            "Answer a read-only question that no structured answer tool covers: a short "
            "summary and at least one citation of a value a read returned. The host checks "
            "each citation and labels the answer grounded, not verified. This grants no "
            "approval or authority."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "minLength": 1, "maxLength": 4000},
                CITATIONS: citations,
            },
            "required": ["summary", CITATIONS],
            "additionalProperties": False,
        },
    )


def citations_of(raw: Any) -> tuple[Citation, ...] | str:
    """The citations a call names, or `CITATION_REFUSAL`."""
    if not isinstance(raw, list):
        return CITATION_REFUSAL
    try:
        return tuple(Citation.model_validate(item) for item in raw)
    except (ValidationError, ValueError, TypeError):
        return CITATION_REFUSAL


def rationale_of(raw: Any) -> ProposalRationale | str:
    """The rationale a call names, or `RATIONALE_REFUSAL`."""
    if not isinstance(raw, dict):
        return RATIONALE_REFUSAL
    try:
        return ProposalRationale.model_validate(raw)
    except (ValidationError, ValueError, TypeError):
        return RATIONALE_REFUSAL


def grounded_arguments(
    args: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[Citation, ...]] | str:
    """The generic answer's arguments and citations, or `GROUNDED_REFUSAL`. The kernel
    checks the summary and every citation again; this only makes the refusal precise."""
    arguments = {k: v for k, v in args.items() if k != CITATIONS}
    citations = citations_of(args.get(CITATIONS))
    if isinstance(citations, str) or not citations:
        return GROUNDED_REFUSAL
    return arguments, citations
