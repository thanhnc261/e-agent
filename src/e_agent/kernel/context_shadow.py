"""``features.context_assembler: shadow`` (ADR 0032 §7, Task 3d.3, Review Focus 8).

Before each driver turn of a run pinned ``shadow`` (each run-loop turn and the post-write
acknowledgement turn) the kernel builds the context pack (`assemble`) and the same inputs
unbounded; after the turn it records ``context.compared``. The acknowledgement turn is
numbered ``cont.turns + 1`` and marked ``acknowledgement``; it moves no continuation counter.
The driver keeps its own history and never sees either pack. Shadow adds no model call, no
provider read and no budget use: its inputs are the run's own records (events, steps and the
continuation), read from the store outside `_timed`, and its token counts are the kernel's
estimator, never a model or tokenizer call. A shadow error records ``context.shadow_failed``
with its stage and a fixed message and changes nothing else: reading its inputs (the store's
events and steps, the driver's token count), assembling and comparing are all guarded, so a
failure there never ends or skips the turn (review D3-30). Only the write of the event itself
can raise, as any other event write of the turn would.

The sources of `assemble`'s per-turn arguments (plan ruling D3-16), none of them new state:

- ``observation_turns``: each ``context.compared`` or ``context.shadow_failed`` event marks
  the end of its driver turn, and the reads that turn requested are recorded after it, so a
  read's turn is the latest marker before its first ``read.recorded`` event
  (`observation_turns`). A read with no marker before it has an unknown age and is never
  cleared. The re-read before dispatch keeps the request id, and the first turn stays.
- ``referenced_evidence``: the evidence ids every ``proposal.created`` event bound (the
  action's approved facts, ADR 0031 §3), and the current evidence of the same requests, so
  a re-read before dispatch stays referenced (`referenced_evidence`).
- ``deferred_pending``: a write proposal of the run is in flight (``pending_action_id``).
- ``rule_texts``: none. The kernel cannot reach the rule inventory without importing a plugin,
  so a validator message stays masked on a hosted route without ``data_processing``.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from e_agent.contracts.context_pack import (
    ContextLayer,
    ContextPack,
    ContextPolicy,
    DroppedKind,
    DroppedReason,
    tool_return_text,
)
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.features import FeatureMode
from e_agent.contracts.run import RunRecord
from e_agent.sdk.ports import DriverInput, Observation
from e_agent.sdk.store import EventSpec

from .context import assemble, estimate_tokens
from .continuation import _Continuation
from .features import context_shadow_failed_event
from .ir_on import IrOnMixin
from .progress import project_progress

SHADOW_POLICY = ContextPolicy()
"""The Phase 3 policy: the record's defaults, the same for every run (ADR 0032 §1)."""

_UNLIMITED = 2**53
UNBOUNDED_POLICY = ContextPolicy(
    max_input_tokens=_UNLIMITED,
    layer_budgets={layer: _UNLIMITED for layer in ContextLayer},
    max_tool_output_tokens=_UNLIMITED,
)
"""The same inputs with no bound, budget or clearing (and no turn, so nothing is old). The
route's class rule still applies: masking is the route's, not a bound."""

TURN_MARKERS = frozenset({RunEventType.CONTEXT_COMPARED, RunEventType.CONTEXT_SHADOW_FAILED})


def observation_turns(events: Iterable[RunEvent], request_ids: Collection[str]) -> dict[str, int]:
    """The driver turn each of ``request_ids`` returned on: the ``turn`` of the latest turn
    marker before its first ``read.recorded`` event. A read before any marker is left out."""
    turns: dict[str, int] = {}
    turn: int | None = None
    for event in sorted(events, key=lambda e: e.sequence):
        if event.type in TURN_MARKERS:
            turn = int(event.payload["turn"])
        elif event.type is RunEventType.READ_RECORDED and turn is not None:
            request_id = event.payload.get("request_id")
            if request_id in request_ids:
                turns.setdefault(str(request_id), turn)
    return turns


def referenced_evidence(
    events: Sequence[RunEvent], observations: Mapping[str, Observation]
) -> frozenset[str]:
    """The evidence ids the run's proposals bound (``proposal.created`` ``evidence_ids``),
    plus the current evidence of each request one of them was read for."""
    bound = {
        str(evidence_id)
        for event in events
        if event.type is RunEventType.PROPOSAL_CREATED
        for evidence_id in event.payload.get("evidence_ids", ())
    }
    requests = {
        event.payload.get("request_id")
        for event in events
        if event.type is RunEventType.READ_RECORDED and event.payload.get("evidence_id") in bound
    }
    current = {o.evidence.evidence_id for r, o in observations.items() if r in requests}
    return frozenset(bound | current)


def layer_tokens(pack: ContextPack) -> dict[str, int]:
    """The kernel's estimate per layer. ``evidence`` is the read-error text plus every
    observation's tool return, as the assembler budgets it; a layer with nothing is left out."""
    layers = {**pack.stable_prefix, **pack.dynamic_suffix}
    tokens = {ContextLayer(layer).value: estimate_tokens(text) for layer, text in layers.items()}
    if pack.observations:
        returns = sum(estimate_tokens(tool_return_text(o)) for o in pack.observations)
        evidence = ContextLayer.EVIDENCE.value
        tokens[evidence] = tokens.get(evidence, 0) + returns
    return tokens


def compared_payload(
    pack: ContextPack,
    unbounded: ContextPack,
    *,
    turn: int,
    tokens_used_delta: int | None,
    acknowledgement: bool = False,
) -> dict[str, Any]:
    """The ``context.compared`` payload: ids, counts, a digest and estimates, never a value
    (PR-26). ``tokens_used_delta`` is None when the driver reports no token use."""
    omitted = [d.ref for d in pack.dropped if d.kind is DroppedKind.OBSERVATION]
    return {
        "turn": turn,
        "acknowledgement": acknowledgement,
        "pack_digest": pack.digest,
        "pack_tokens": layer_tokens(pack),
        "unbounded_tokens": layer_tokens(unbounded),
        "tokens_used_delta": tokens_used_delta,
        "observations": len(pack.observations),
        "dropped": {k.value: sum(d.kind is k for d in pack.dropped) for k in DroppedKind},
        "drop_reasons": {r.value: sum(d.reason is r for d in pack.dropped) for r in DroppedReason},
        "omitted_evidence": omitted,
        "truncated_evidence": [
            o.evidence.evidence_id
            for o in pack.observations
            if o.truncated and o.evidence.evidence_id not in omitted
        ],
        "masked_evidence": [o.evidence.evidence_id for o in pack.observations if o.masked],
    }


@dataclass(frozen=True)
class ShadowTurn:
    """One turn's shadow work, carried from before the driver call to after it."""

    turn: int
    tokens_before: int | None
    pack: ContextPack | None = None
    unbounded: ContextPack | None = None
    failed: str | None = None
    """The stage that failed (`CONTEXT_SHADOW_MESSAGES`), or None."""
    acknowledgement: bool = False
    """The post-write acknowledgement turn (`_finish_verified`), not a run-loop turn."""


class ContextShadowMixin(IrOnMixin):
    def _driver_tokens(self, run_id: str) -> int | None:
        """The driver's own count, or None when it reports none (unknown, not zero)."""
        tokens_used = getattr(self._driver, "tokens_used", None)
        return None if tokens_used is None else int(tokens_used(run_id))

    async def _context_shadow(
        self,
        run: RunRecord,
        cont: _Continuation,
        step_input: DriverInput,
        *,
        acknowledgement: bool = False,
    ) -> ShadowTurn | None:
        """The pack for the turn about to run, for a run pinned ``shadow``; None otherwise."""
        if self._run_modes(cont).context_assembler is not FeatureMode.SHADOW:
            return None
        turn = cont.turns + 1 if acknowledgement else cont.turns
        before: int | None = None
        ack = acknowledgement
        try:  # a shadow error, a store read's included, never reaches the live path
            before = self._driver_tokens(run.run_id)
            events = await self._store.list_events(run.tenant_id, run.run_id)
            steps = await self._store.list_steps(run.tenant_id, run.run_id)
            ledger = project_progress(events, steps)
            turns = observation_turns(events, cont.observations.keys())
            referenced = referenced_evidence(events, cont.observations)
            task = cont.task if cont.task is not None else self._run_task(run)
            allowed = self._allowed(run, cont)
            tool_set = tuple(self._registry.capabilities) if allowed is None else allowed
        except Exception:
            return ShadowTurn(turn, before, failed="inputs", acknowledgement=ack)
        observations = tuple(cont.observations.values())
        errors: Mapping[str, str] = dict(cont.read_errors)
        common: dict[str, Any] = {"task": task, "tool_set": tool_set}
        try:
            pack = assemble(
                SHADOW_POLICY,
                ledger,
                observations,
                errors,
                step_input.findings,
                self._registry.data_classes,
                self._route,
                turn=turn,
                observation_turns=turns,
                deferred_pending=cont.pending_action_id is not None,
                referenced_evidence=referenced,
                **common,
            )
            unbounded = assemble(
                UNBOUNDED_POLICY,
                ledger,
                observations,
                errors,
                step_input.findings,
                self._registry.data_classes,
                self._route,
                **common,
            )
        except Exception:
            return ShadowTurn(turn, before, failed="assemble", acknowledgement=ack)
        return ShadowTurn(turn, before, pack, unbounded, acknowledgement=ack)

    async def _record_context_shadow(self, run: RunRecord, shadow: ShadowTurn) -> RunRecord:
        """Append the turn's ``context.compared`` (or ``context.shadow_failed``) after the
        driver returned; only the run revision moves."""
        event: EventSpec
        ack = shadow.acknowledgement
        if shadow.pack is None or shadow.unbounded is None:
            stage = shadow.failed or "assemble"
            event = context_shadow_failed_event(stage, shadow.turn, acknowledgement=ack)
        else:
            try:
                after, before = self._driver_tokens(run.run_id), shadow.tokens_before
                delta = None if after is None or before is None else after - before
                payload = compared_payload(
                    shadow.pack,
                    shadow.unbounded,
                    turn=shadow.turn,
                    tokens_used_delta=delta,
                    acknowledgement=ack,
                )
                event = (RunEventType.CONTEXT_COMPARED, payload, None)
            except Exception:
                event = context_shadow_failed_event("compare", shadow.turn, acknowledgement=ack)
        run = await self._store.get_run(run.tenant_id, run.run_id)
        return await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}), run.revision, [event]
        )
