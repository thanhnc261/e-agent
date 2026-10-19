"""``features.grounded_answers`` for write proposals and plans: the checked
`ProposalRationale` (ADR 0033 §4, §5, Task 3e.3, D6, Review Focus 5 and 7).

**The check** (`check_rationale`, pure). A rationale's evidence id resolves when it names an
observation of **this run** (the kernel passes the run's continuation observations, never
the store or the tenant: Review Focus 5, threat T6). A rule id resolves when it is a kernel
finding id (``KERNEL-*``) or a rule of the admitted rule inventory (ADR 0009): the union of
every admitted plugin's ``PluginContribution.rule_inventory`` (`PluginRegistry`). The check
runs before the proposal is validated and before an action exists, so a refused rationale
never reaches a validator. It makes no provider read and no model call.

**Per the run's pinned mode** (`_run_modes`, `_rationale_probe`):

- ``off``: today. The rationale is dropped: nothing is checked, recorded or stored, and no
  validator, digest or plan sees it.
- ``shadow``: the proposal takes today's path. Its own write (``proposal.created``) carries
  the rationale at rest and ``grounding.compared`` (counts only). A check error records
  ``grounding.shadow_failed`` (stage ``rationale``, a fixed message) and changes nothing else.
- ``on``: an evidence id or rule id that does not resolve is the repair finding
  ``KERNEL-RATIONALE`` (one per id: the id, a fixed message, never model text), returned
  within ``max_validation_repairs`` and recorded in ``validation.completed`` with no action
  id as the id's digest (`repair_at_rest`, Task 3.R1). A rationale that resolves changes
  nothing: validation, policy, approval and dispatch are today's. It can only add a finding.

Rationale is never an approval input and never in the approval digest (target §5.6): every
validator, digest input and stored plan gets the proposal or plan without it
(`strip_grounding`, `strip_plan`). **At rest** (owner G2, PR-26) it is codes, the
``jcs-sha256-v1`` digest of each model-authored text, and each id verbatim only when it
resolved, else only its digest (`at_rest`, `kernel/at_rest.py`, Task 3.R1): ``rationale``
and, for a plan's steps, ``step_rationales`` in ``proposal.created``. The texts live only in
the run's continuation (``rationale``, ``step_rationales``), for the approval card.

**Failure** (ADR 0027): a check that cannot run in ``on`` records ``feature.fallback``
``GROUNDING_CHECK_FAILED`` before the run's first reservation, and the proposal goes on as
today with its rationale dropped; after one, the run fails closed with
``GROUNDING_UNAVAILABLE``, in reconciliation while a reservation is unresolved
(`_end_closed`). No event carries exception text or rationale text.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from e_agent.contracts.digest import digest
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode
from e_agent.contracts.grounding import (
    GroundingCompared,
    ProposalRationale,
    RationaleCounts,
    RefCounts,
)
from e_agent.contracts.plan import ActionPlan, ActionProposal
from e_agent.contracts.run import ReasonCode, RunRecord
from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.sdk.ports import DriverInput
from e_agent.sdk.store import EventSpec

from .at_rest import (
    finding_at_rest,
    goal_at_rest,
    known_goals,
    refs_at_rest,
    repair_at_rest,
    rule_stored,
)
from .context import KERNEL_RULE_PREFIX
from .continuation import _Continuation
from .grounded_answer import GroundedAnswerMixin

KERNEL_RATIONALE = "KERNEL-RATIONALE"


class RefKind(StrEnum):
    EVIDENCE = "evidence"
    RULE = "rule"


RATIONALE_MESSAGES = MappingProxyType(
    {
        RefKind.EVIDENCE: "This rationale names evidence that is not an observation of this "
        "run; cite the evidence ids this run read.",
        RefKind.RULE: "This rationale names a rule that is not in the admitted rule "
        "inventory and is no kernel finding id.",
    }
)
"""The fixed message of each ``KERNEL-RATIONALE`` repair finding, by the kind of id."""
RATIONALE_SHADOW_MESSAGE = "The rationale check could not run."
"""The fixed ``grounding.shadow_failed`` message of the ``rationale`` stage."""

Entry = tuple[str | None, ProposalRationale]
"""A rationale and where it sits: None for the proposal's or the plan's own, else a step id."""


def at_rest(rationale: ProposalRationale, result: RationaleResult) -> dict[str, Any]:
    """The stored form (owner G2, Task 3.R1): codes and a digest of each model-authored text;
    the goal verbatim only when ``result`` knows it, and the evidence and rule ids verbatim
    only when they resolved (a ``KERNEL-*`` id only when the kernel emits it), else only
    their digests (`kernel/at_rest.py`)."""
    evidence = {ref for ref, ok in result.evidence if ok}
    rules = {ref for ref, ok in result.rules if ok and rule_stored(ref)}  # review R1-1
    return {
        **goal_at_rest(rationale.goal_ref, result.goals),
        **refs_at_rest(
            "cited_evidence", "unresolved_evidence_digests", rationale.cited_evidence, evidence
        ),
        **refs_at_rest(
            "rules_considered", "unresolved_rule_digests", rationale.rules_considered, rules
        ),
        "alternatives": [
            {
                "proposal_digest": a.proposal_digest,
                "reason_code": a.reason_code.value,
                "line_digest": digest(a.line),
            }
            for a in rationale.alternatives
        ],
        "summary_digest": digest(rationale.summary),
    }


@dataclass(frozen=True)
class RationaleResult:
    """Each named id and whether it resolved, in rationale order."""

    evidence: tuple[tuple[str, bool], ...]
    rules: tuple[tuple[str, bool], ...]
    goals: frozenset[str] = frozenset()
    """The goal refs stored verbatim (`known_goals`); a goal is never checked or refused."""

    @property
    def resolved(self) -> bool:
        return all(ok for _, ok in (*self.evidence, *self.rules))

    def counts(self) -> RationaleCounts:
        def count(refs: tuple[tuple[str, bool], ...]) -> RefCounts:
            resolved = sum(ok for _, ok in refs)
            return RefCounts(cited=len(refs), resolved=resolved, unresolved=len(refs) - resolved)

        return RationaleCounts(evidence=count(self.evidence), rules=count(self.rules))

    def findings(self, stored: bool = False) -> tuple[Finding, ...]:
        """One ``KERNEL-RATIONALE`` per id that did not resolve: the id, never model text;
        ``stored``: as recorded, the id's digest and no evidence id (Task 3.R1)."""

        def finding(kind: RefKind, ref: str) -> Finding:
            raw = Finding(
                rule_id=KERNEL_RATIONALE,
                rule_version="1",
                status=ValidationStatus.FAIL,
                message=RATIONALE_MESSAGES[kind],
                observed=ref,
                evidence_ids=(ref,) if kind is RefKind.EVIDENCE else (),
            )
            return finding_at_rest(raw) if stored else raw

        return (
            *(finding(RefKind.EVIDENCE, ref) for ref, ok in self.evidence if not ok),
            *(finding(RefKind.RULE, ref) for ref, ok in self.rules if not ok),
        )


def check_rationale(
    rationales: Iterable[ProposalRationale],
    evidence_ids: Collection[str],
    known_rules: Collection[str],
    goals: frozenset[str] = frozenset(),
) -> RationaleResult:
    """Each named evidence id against ``evidence_ids`` (this run's observations) and each
    rule id against ``known_rules`` or the ``KERNEL-*`` prefix; ``goals`` are carried for
    the stored form. Pure."""
    evidence: list[tuple[str, bool]] = []
    rules: list[tuple[str, bool]] = []
    for rationale in rationales:
        evidence.extend((ref, ref in evidence_ids) for ref in rationale.cited_evidence)
        rules.extend(
            (ref, ref.startswith(KERNEL_RULE_PREFIX) or ref in known_rules)
            for ref in rationale.rules_considered
        )
    return RationaleResult(tuple(evidence), tuple(rules), goals)


def strip_grounding(proposal: ActionProposal) -> ActionProposal:
    """The proposal without its kernel envelope: what validators and digests see."""
    return proposal.model_copy(update={"citations": (), "rationale": None})


def strip_plan(plan: ActionPlan) -> ActionPlan:
    """The plan without any rationale or citation, at the plan or a step (3e.1 carry)."""
    steps = tuple(
        s.model_copy(update={"proposal": strip_grounding(s.proposal)}) for s in plan.steps
    )
    return plan.model_copy(update={"steps": steps, "rationale": None})


def proposal_entries(proposal: ActionProposal) -> tuple[Entry, ...]:
    return () if proposal.rationale is None else ((None, proposal.rationale),)


def plan_entries(plan: ActionPlan) -> tuple[Entry, ...]:
    """A plan's rationales: its own, then each step's. A 1-step plan is today's proposal, so
    with no plan rationale its step's is the proposal's own."""
    steps: list[Entry] = [
        (s.step_id, s.proposal.rationale) for s in plan.steps if s.proposal.rationale
    ]
    if plan.rationale is None and len(plan.steps) == 1:
        return tuple((None, r) for _, r in steps)
    return (*(((None, plan.rationale),) if plan.rationale else ()), *steps)


@dataclass(frozen=True)
class RationaleProbe:
    """What the check found before the action exists: the mode it acts in (``off`` when
    nothing is recorded or stored), the checked rationales and their result, whether a
    shadow check failed, and the run when a fallback moved its revision."""

    mode: FeatureMode
    entries: tuple[Entry, ...] = ()
    result: RationaleResult | None = None
    failed: bool = False
    run: RunRecord | None = None

    @property
    def _kept(self) -> bool:
        return self.mode is not FeatureMode.OFF and not self.failed and bool(self.entries)

    def stored(self) -> dict[str, Any]:
        """The ``proposal.created`` keys: the at-rest rationale and step rationales."""
        if not self._kept or self.result is None:
            return {}
        keys: dict[str, Any] = {}
        steps = {step: at_rest(r, self.result) for step, r in self.entries if step is not None}
        top = [r for step, r in self.entries if step is None]
        if top:
            keys["rationale"] = at_rest(top[0], self.result)
        if steps:
            keys["step_rationales"] = steps
        return keys

    def events(self, action_id: str | None) -> list[EventSpec]:
        """``shadow`` only, with a rationale: ``grounding.compared`` or
        ``grounding.shadow_failed``, written with the proposal's ``proposal.created``, or with
        no action id in the write of a rejection after the probe ran (Codex C1-1)."""
        if self.mode is not FeatureMode.SHADOW or not self.entries:
            return []
        if self.failed or self.result is None:
            payload = {"stage": "rationale", "message": RATIONALE_SHADOW_MESSAGE}
            return [(RunEventType.GROUNDING_SHADOW_FAILED, payload, action_id)]
        payload = GroundingCompared(rationale=self.result.counts()).model_dump(mode="json")
        return [(RunEventType.GROUNDING_COMPARED, payload, action_id)]

    def keep(self, cont: _Continuation) -> None:
        """Keep the texts in the continuation for the approval card, or clear the last."""
        kept = self.entries if self._kept else ()
        cont.rationale = next((r for step, r in kept if step is None), None)
        cont.step_rationales = {step: r for step, r in kept if step is not None}


class RationaleMixin(GroundedAnswerMixin):
    async def _rationale_probe(
        self,
        run: RunRecord,
        cont: _Continuation,
        entries: Sequence[Entry],
    ) -> RationaleProbe | RunRecord | DriverInput:
        """Check a proposal's or plan's rationales before it is validated and before its
        action exists. A `RationaleProbe` continues today's path; in ``on`` an id that does not
        resolve returns its ``KERNEL-RATIONALE`` repair, and a check that cannot run after a
        reservation returns the closed run."""
        mode = self._run_modes(cont).grounded_answers
        if mode is FeatureMode.OFF or not entries:
            return RationaleProbe(FeatureMode.OFF)  # dropped, never stored
        entries = tuple(entries)
        try:
            evidence = {o.evidence.evidence_id for o in cont.observations.values()}
            rationales = [r for _, r in entries]
            goals = known_goals(run.task_id, run.task_version)
            result = check_rationale(rationales, evidence, self._registry.rule_inventory, goals)
        except Exception:  # no exception text reaches an event (PR-25, PR-28)
            if mode is FeatureMode.SHADOW:
                return RationaleProbe(mode, entries, failed=True)
            events = await self._store.list_events(run.tenant_id, run.run_id)
            if any(e.type is RunEventType.ACTION_RESERVED for e in events):
                return await self._end_closed(run, ReasonCode.GROUNDING_UNAVAILABLE)
            current = await self._store.get_run(run.tenant_id, run.run_id)
            current = await self.record_fallback(
                current, "grounded_answers", ReasonCode.GROUNDING_CHECK_FAILED
            )
            return RationaleProbe(FeatureMode.OFF, run=current)  # as today, dropped
        if mode is FeatureMode.ON and not result.resolved:
            current = await self._store.get_run(run.tenant_id, run.run_id)
            return await repair_at_rest(self._repair_finding, current, cont, result)
        return RationaleProbe(mode, entries, result)
