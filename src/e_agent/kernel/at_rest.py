"""Model-authored refs at rest (Task 3.R1, phase review P-1, P-2, PR-26).

A ref the model names is model text, and it can hold a value (an email, a phone number, an
order number). It is stored verbatim only when the kernel resolved it against something it
already knows, and otherwise only as its ``jcs-sha256-v1`` digest under a key that says so:

- a rationale's ``goal_ref`` when it is ``run`` or the run's task definition ``id@version``
  (`known_goals`), else ``goal_ref_digest`` (`goal_at_rest`);
- its evidence and rule ids the check resolved, in order, else only their digests under
  ``unresolved_evidence_digests`` and ``unresolved_rule_digests``, left out when empty and
  never mixed into the id lists (`refs_at_rest`);
- a citation's evidence id and pointer when they named a value of this run's evidence,
  whatever its status, else ``evidence_id_digest`` and ``pointer_digest``
  (`citation_at_rest`).

The record accepts any such ref and the kernel refuses none for its shape: an unresolved
ref stays a repair, never a refused proposal. A repair finding that names a ref goes back
to the model with the raw ref so it can correct it; the finding as recorded, in
``validation.completed`` and in the stored continuation, holds the digest as ``observed`` and
no evidence id that did not resolve (`finding_at_rest`, `repair_at_rest`).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Awaitable, Callable, Collection, Iterable
from typing import Protocol

from e_agent.contracts.digest import digest
from e_agent.contracts.run import RunRecord
from e_agent.contracts.validation import Finding
from e_agent.sdk.ports import DriverInput

from .continuation import _Continuation

RUN_GOAL = "run"

Repair = Callable[
    [RunRecord, _Continuation, tuple[Finding, ...]], Awaitable[RunRecord | DriverInput]
]


def known_goals(task_id: str | None, task_version: str | None) -> frozenset[str]:
    """The goal refs a run's rationale may name verbatim: ``run``, and the ``id@version`` of
    the definition the run is bound to."""
    if task_id is None:
        return frozenset({RUN_GOAL})
    return frozenset({RUN_GOAL, f"{task_id}@{task_version}"})


def goal_at_rest(goal_ref: str, goals: Collection[str]) -> dict[str, str]:
    return {"goal_ref": goal_ref} if goal_ref in goals else {"goal_ref_digest": digest(goal_ref)}


def refs_at_rest(
    ids_key: str, digests_key: str, refs: Iterable[str], resolved: Collection[str]
) -> dict[str, list[str]]:
    """The resolved refs in order under ``ids_key``; the digest of each other one under
    ``digests_key``, which is left out when there is none."""
    refs = tuple(refs)
    stored = {ids_key: [ref for ref in refs if ref in resolved]}
    unresolved = [digest(ref) for ref in refs if ref not in resolved]
    if unresolved:
        stored[digests_key] = unresolved
    return stored


def citation_at_rest(
    evidence_id: str, pointer: str, value_digest: str, *, named: bool
) -> dict[str, str]:
    if named:
        refs = {"evidence_id": evidence_id, "pointer": pointer}
    else:
        refs = {"evidence_id_digest": digest(evidence_id), "pointer_digest": digest(pointer)}
    return {**refs, "value_digest": value_digest}


def finding_at_rest(finding: Finding, *, digested: bool = True) -> Finding:
    """A finding whose ref resolved nothing, as recorded: its ``observed`` ref as a digest
    and no evidence id; unchanged when not ``digested``."""
    if not digested:
        return finding
    observed = None if finding.observed is None else digest(finding.observed)
    return finding.model_copy(update={"observed": observed, "evidence_ids": ()})


class Checked(Protocol):
    """A check result whose findings name model refs (`RationaleResult`, `GroundingResult`)."""

    def findings(self, stored: bool = False) -> tuple[Finding, ...]: ...


async def repair_at_rest(
    repair: Repair, run: RunRecord, cont: _Continuation, checked: Checked
) -> RunRecord | DriverInput:
    """``repair`` (`_repair_finding`) recording the findings as stored in
    ``validation.completed`` and the continuation, with the raw findings returned to the
    model so it can correct its refs."""
    cont.findings = checked.findings(stored=True)
    result = await repair(run, cont, cont.findings)
    if isinstance(result, DriverInput):
        return dataclasses.replace(result, findings=checked.findings())
    return result
