"""``features.kernel_repeat``: ``KERNEL-REPEAT`` for a repeated blocked proposal (ADR 0031 §5,
Task 3d.6, Review Focus 6 and 7).

**The rule.** A write proposal in `_handle_proposal` is a repeat when an earlier write
proposal of the same run was blocked there by validation (policy permitted, a digest that is
not the sentinel ``invalid``, and no validator that raised: an ``error`` bundle has not
judged the facts), and both hold:

- its approval digest input, with the earlier revision's rule bundle version, digests to the
  earlier action's ``digest``. The input covers the contract, binding, connection and its
  version, credential subject and version, arguments, expected effects, policy version and,
  for every observation the validation saw, its evidence id, source, revision, completeness
  and a revision-less fact's ``fact_digest``: a re-read with a new revision (or a new evidence
  id) is validated again (Review Focus 6);
- the registry surface digest is the run's ``surface_digest``, so the validators and their
  bundles are the ones the earlier validation ran.

The check runs before `_validate`, the single merge point of validator results (review
D3-10), only for a proposal whose policy decision permits it: a denial keeps today's path.
A multi-step plan's steps never reach it: a step blocked in `_plan_contexts` makes no action
or digest, and later steps revalidate in `_dispatch`. A 1-step plan is a single proposal.

**Modes** (pinned per run, `_run_modes`):

- ``off``: today. Nothing is recorded or kept (`BlockedRevision`s are kept only otherwise).
- ``shadow``: validation runs as today, and the proposal's own write carries
  ``repeat.compared`` (``would_repeat``, ``repeat_of``, ``same_findings``: the same rule ids
  and statuses, null without a match). A shadow error records ``repeat.shadow_failed`` with
  its stage and a fixed message instead, and changes nothing else (review D3-30).
- ``on``: a repeat makes no action. ``validation.completed`` (no action id) records FAIL with
  ``KERNEL-REPEAT`` (``observed`` is the earlier action id) and the earlier findings,
  returned as a repair within ``max_validation_repairs``, as `_repair_finding` does.

**Failure** (ADR 0027): a check that cannot run in ``on`` records ``feature.fallback``
``REPEAT_CHECK_FAILED`` before the run's first reservation (no ``action.reserved`` event),
and the proposal is validated as today; after one, the run fails closed with
``REPEAT_UNAVAILABLE``, in reconciliation while a reservation is unresolved (`_end_closed`).
No event carries exception text, a value or model text (PR-26).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.digest import CanonicalizationError
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import ReasonCode, RunRecord
from e_agent.contracts.validation import Finding, ValidationResult, ValidationStatus
from e_agent.sdk.ports import DriverInput
from e_agent.sdk.store import EventSpec

from .approval import compute_digest
from .continuation import BlockedRevision, _Continuation
from .ir_on import IrOnMixin

EVIDENCE_BUNDLE, NO_VALIDATOR_BUNDLE, ERROR_BUNDLE = "kernel-evidence-v1", "none", "error"
SENTINEL_BUNDLES = frozenset({EVIDENCE_BUNDLE, NO_VALIDATOR_BUNDLE, ERROR_BUNDLE})
"""The rule bundle versions `_validate` reports when no domain rule ran: incomplete
evidence, no validator, a validator that raised or claimed a kernel rule id. None is a
real bundle to bind; an ``error`` block is never a repeat."""
INVALID_DIGEST = "invalid"
"""The digest of a proposal outside the digest profile (``KERNEL-ARGS``)."""

KERNEL_REPEAT = "KERNEL-REPEAT"
REPEAT_MESSAGE = (
    "This proposal repeats one that validation already blocked, on the same facts; "
    "change it or read again."
)
"""The fixed message of the ``KERNEL-REPEAT`` repair finding."""
REPEAT_SHADOW_MESSAGES = MappingProxyType(
    {
        "check": "The repeat check could not run.",
        "compare": "The repeat check could not be compared with validation.",
    }
)
"""Each ``kernel_repeat: shadow`` stage's fixed ``repeat.shadow_failed`` message."""

CanonicalFor = Callable[..., dict[str, Any]]
"""The proposal's approval digest input for a ``rule_bundle_version`` keyword."""


def find_repeat(
    blocked: Sequence[BlockedRevision], canonical_for: CanonicalFor, *, surface_unchanged: bool
) -> BlockedRevision | None:
    """The latest blocked revision the proposal repeats, or None. A proposal outside the
    digest profile is never a repeat."""
    if not surface_unchanged:
        return None
    for revision in reversed(blocked):
        try:
            canonical = canonical_for(rule_bundle_version=revision.rule_bundle_version)
            if compute_digest(canonical) == revision.digest:
                return revision
        except CanonicalizationError:
            return None
    return None


def same_findings(earlier: BlockedRevision, validation: ValidationResult) -> bool:
    """Whether validation returned the earlier revision's rule ids and statuses."""
    return [(f.rule_id, f.status) for f in earlier.findings] == [
        (f.rule_id, f.status) for f in validation.findings
    ]


@dataclass(frozen=True)
class RepeatProbe:
    """What the check found before validation: the mode it acts in (``off`` when nothing is
    recorded), the matched revision, whether a shadow check failed, and the run when a
    fallback moved its revision (final check FA-2)."""

    mode: FeatureMode
    match: BlockedRevision | None = None
    failed: bool = False
    run: RunRecord | None = None


def _shadow_failed(stage: str, action_id: str) -> EventSpec:
    payload = {"stage": stage, "message": REPEAT_SHADOW_MESSAGES[stage]}
    return (RunEventType.REPEAT_SHADOW_FAILED, payload, action_id)


class RepeatMixin(IrOnMixin):
    async def _has_reserved(self, run: RunRecord) -> bool:
        """Whether the run has reserved a write: after one a check that cannot run fails
        closed, never falls back (ADR 0027)."""
        events = await self._store.list_events(run.tenant_id, run.run_id)
        return any(e.type is RunEventType.ACTION_RESERVED for e in events)

    async def _fell_back(self, run: RunRecord, feature: str, reason: ReasonCode) -> RunRecord:
        """``feature.fallback`` on the run's current record; returns the moved record."""
        current = await self._store.get_run(run.tenant_id, run.run_id)
        return await self.record_fallback(current, feature, reason)

    async def _repeats_verified_answer(
        self, cont: _Continuation, proposal: ActionProposal, connection_id: str, digest: str
    ) -> bool:
        """Whether a structured answer repeats the run's last action, already VERIFIED with
        the same contract, connection, digest and arguments (2c.8c; in every mode)."""
        if cont.last_action_id is None:
            return False
        previous = await self._store.get_action(cont.ctx.tenant_id, cont.last_action_id)
        return (
            previous.state is ActionState.VERIFIED
            and previous.contract_id == proposal.contract_id
            and previous.connection_id == connection_id
            and previous.digest == digest
            and previous.arguments == dict(proposal.arguments)
        )

    async def _repeat_probe(
        self, run: RunRecord, cont: _Continuation, canonical_for: CanonicalFor, *, permitted: bool
    ) -> RepeatProbe | RunRecord | DriverInput:
        """Run the repeat check before validation. A `RepeatProbe` continues today's path;
        in ``on`` a repeat returns its ``KERNEL-REPEAT`` repair, and a check that cannot run
        after a reservation returns the closed run."""
        mode = self._run_modes(cont).kernel_repeat
        if mode is FeatureMode.OFF or not permitted:
            return RepeatProbe(FeatureMode.OFF)
        try:
            unchanged = self._registry.surface_digest() == cont.surface_digest
            match = find_repeat(cont.blocked, canonical_for, surface_unchanged=unchanged)
        except Exception:  # no exception text reaches an event (PR-25, PR-28)
            if mode is FeatureMode.SHADOW:
                return RepeatProbe(mode, failed=True)
            if await self._has_reserved(run):
                return await self._end_closed(run, ReasonCode.REPEAT_UNAVAILABLE)
            fell = await self._fell_back(run, "kernel_repeat", ReasonCode.REPEAT_CHECK_FAILED)
            return RepeatProbe(FeatureMode.OFF, run=fell)  # validated as today
        if mode is FeatureMode.ON and match is not None:
            repeated = Finding(
                rule_id=KERNEL_REPEAT,
                rule_version="1",
                status=ValidationStatus.FAIL,
                message=REPEAT_MESSAGE,
                observed=match.action_id,
            )
            cont.findings = (repeated, *match.findings)
            current = await self._store.get_run(run.tenant_id, run.run_id)
            return await self._repair_finding(current, cont, cont.findings)
        return RepeatProbe(mode, match)

    @staticmethod
    def _repeat_events(
        probe: RepeatProbe, validation: ValidationResult, action_id: str
    ) -> list[EventSpec]:
        """``shadow`` only: the proposal's ``repeat.compared``, or ``repeat.shadow_failed``;
        written with ``proposal.created``, so the run's revision is today's."""
        if probe.mode is not FeatureMode.SHADOW:
            return []
        if probe.failed:
            return [_shadow_failed("check", action_id)]
        match = probe.match
        try:
            same = None if match is None else same_findings(match, validation)
        except Exception:  # a shadow error never reaches the live path
            return [_shadow_failed("compare", action_id)]
        payload = {
            "would_repeat": match is not None,
            "repeat_of": None if match is None else match.action_id,
            "same_findings": same,
        }
        return [(RunEventType.REPEAT_COMPARED, payload, action_id)]

    def _remember_blocked(
        self, cont: _Continuation, action: ActionRecord, validation: ValidationResult
    ) -> None:
        """Keep a validation-blocked proposal for the check, when the run is not pinned
        ``off``; never one outside the digest profile, or one a validator that raised or
        returned ERROR blocked: it has not judged the facts (review R1-1)."""
        if self._run_modes(cont).kernel_repeat is FeatureMode.OFF:
            return
        bundles = validation.rule_bundle_version.split("+")
        if (
            action.digest == INVALID_DIGEST
            or ERROR_BUNDLE in bundles
            or validation.status is ValidationStatus.ERROR
        ):
            return
        revision = BlockedRevision(
            action_id=action.action_id,
            digest=action.digest,
            rule_bundle_version=validation.rule_bundle_version,
            findings=validation.findings,
        )
        cont.blocked = (*cont.blocked, revision)
