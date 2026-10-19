"""Grounding records (ADR 0033): a citation that ties a claim to this run's evidence.

A `Citation` is model output, a claim the kernel checks: it names an observation of the run
by ``evidence_id``, an RFC 6901 ``pointer`` into that observation's ``data``, and the
``value`` the model says is there. It travels in the kernel envelope beside a proposal's
arguments (`ActionProposal.citations`), never inside them, so a domain answer model is
unchanged. It never grants approval, changes policy or marks anything verified (PR-13).

The record accepts any pointer text up to `POINTER_MAX` (and an evidence id up to
`EVIDENCE_ID_MAX`): a pointer that is not RFC 6901, or that names nothing, is an unresolved
citation the kernel returns as a repair, never a refused proposal. The value must be a JSON
value, so the kernel can always digest it (ADR 0006). At rest a citation is its value
digest, never the value, with its evidence id and pointer verbatim only when they named a
value of this run's evidence; otherwise their digests (PR-26, Task 3.R1, `kernel/at_rest.py`).

A `ProposalRationale` (ADR 0033 §4) is model output too, on a write proposal or a plan: the
goal it serves, the evidence ids and rule ids it rests on, the alternatives it rejected and
a short summary. The kernel checks its ids and never lets it grant, gate or change anything
(PR-13, target §5.6). The record accepts any id that names nothing (the kernel returns that
as a repair), but every id-like field must have an id's shape, never prose. At rest (owner
G2, PR-26, Task 3.R1) it is codes, a digest of each text, and each id verbatim only when
the kernel resolved it; an id that resolved nothing is stored only as its digest, so a
value-shaped token the model put in an id field is never stored.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal
from typing import Annotated, Any

from pydantic import Field, StringConstraints, field_validator

from .common import Record
from .run import ReasonCode


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


EVIDENCE_ID_MAX = 128
"""The longest citation evidence id the record accepts (Task 3.R1)."""
POINTER_MAX = 1024
"""The longest citation pointer the record accepts (Task 3.R1)."""


class Citation(Record):
    """One claim that ``value`` is at ``pointer`` in the data of this run's observation
    ``evidence_id`` (ADR 0033 §1)."""

    evidence_id: Annotated[str, StringConstraints(max_length=EVIDENCE_ID_MAX)]
    pointer: Annotated[str, StringConstraints(max_length=POINTER_MAX)]
    """An RFC 6901 JSON pointer into the observation's ``data``; ``""`` is the whole data."""
    value: Any
    """The value the model claims is there; compared under ``jcs-sha256-v1``, never stored."""

    @field_validator("value")
    @classmethod
    def _json_value(cls, value: Any) -> Any:
        _check_json(value)
        return value


RefId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.:@#/+-]{1,128}$")]
"""An id named by a rationale (a goal, an evidence id, a rule id): no whitespace, no prose."""
SUMMARY_MAX = 400
"""The longest rationale summary the record accepts (ADR 0033 §4)."""


class RejectedAlternative(Record):
    """An alternative the model considered and did not propose: the digest of its proposal,
    why it was rejected, and one model-authored line."""

    proposal_digest: Annotated[str, StringConstraints(pattern=r"^jcs-sha256-v1:[0-9a-f]{64}$")]
    reason_code: ReasonCode
    line: Annotated[str, StringConstraints(max_length=SUMMARY_MAX, pattern=r"^[^\r\n]*$")]
    """One line of model text: shown as model-authored, stored only as its digest."""


class ProposalRationale(Record):
    """Why a write proposal or a plan is proposed (ADR 0033 §4): checked model output, never
    an approval input and never in the approval digest."""

    goal_ref: RefId
    """``run``, or the run's task definition ``id@version``: never refused, and stored and
    shown verbatim only when it is one of those two; any other value is stored as its
    digest (Task 3.R1)."""
    cited_evidence: tuple[RefId, ...] = ()
    """Evidence ids of this run's observations."""
    rules_considered: tuple[RefId, ...] = ()
    """Rule ids of the admitted rule inventory (ADR 0009), or kernel finding ids."""
    alternatives: tuple[RejectedAlternative, ...] = ()
    summary: str = Field(max_length=SUMMARY_MAX)
    """Model-authored text: shown as such, stored only as its digest."""


class RefCounts(Record):
    """How many named refs of one kind resolved."""

    cited: int = 0
    resolved: int = 0
    unresolved: int = 0


class CitationCounts(RefCounts):
    mismatched: int = 0
    verdicts: tuple[str, ...] = ()
    """Each citation's status, in citation order; never a value."""


class RationaleCounts(Record):
    evidence: RefCounts = RefCounts()
    rules: RefCounts = RefCounts()


class GroundingCompared(Record):
    """The one ``grounding.compared`` payload (ADR 0033 §5), for a typed answer's citations
    and for a write proposal's or plan's rationale alike: counts and statuses only, never a
    value or model text (PR-26). The part a proposal does not carry is all zeros."""

    citations: CitationCounts = CitationCounts()
    rationale: RationaleCounts = RationaleCounts()
