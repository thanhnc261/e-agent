"""``features.context_assembler: on`` (ADR 0032 §7, Task 3d.5, Review Focus 4 and 7).

Every driver call of a run pinned ``on`` (each run-loop turn and the post-write
acknowledgement turn) passes the turn's pack in ``DriverInput.context``, built by `assemble`
from the same records ``shadow`` reads (`_pack_inputs`). After the call the kernel records
``context.assembled``: the turn, the pack digest and counts, never a value (PR-26). It marks
the turn as ``context.compared`` does in shadow, so a read's age for clearing comes from the
events (`observation_turns`), and it is the durable record of the pack digests and drop log
ADR 0032 §13 names. A turn that fell back records no marker: its reads count from the
previous marker (cleared at most one turn early) or, with none before, are never cleared.

Failure handling (ADR 0032 §7, ADR 0027). When the pack cannot be built:

- before the run's first write reservation (no ``action.reserved`` event), on a route that is
  ``local`` or declares ``data_processing``: ``feature.fallback`` with
  ``CONTEXT_ASSEMBLY_FAILED``, and the call uses the driver's own history;
- otherwise no fallback (`ContextUnavailable`): the acknowledgement turn is skipped with
  ``context.failed``, and any other call ends the run ``CONTEXT_UNAVAILABLE``, in
  reconciliation while a reservation is unresolved (`_end_closed`).

A driver that cannot render a turn from its pack raises ``ContextNotRendered`` (review
D3-42), mapped the same way, never retried without the pack. The route check runs first, so
a refused route makes no assembly and records no fallback. A fallback never bypasses
approval, admission, verification or the transition table: it only changes what the one
call is given.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from e_agent.contracts.context_pack import ContextPack, DroppedKind, DroppedReason
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode
from e_agent.contracts.run import ReasonCode, RunRecord
from e_agent.sdk.ports import DriverInput

from .context import assemble
from .context_shadow import SHADOW_POLICY, ContextShadowMixin, layer_tokens
from .continuation import _Continuation
from .features import unmasked_allowed

ON_POLICY = SHADOW_POLICY
"""The Phase 3 policy: the record's defaults, the same for every run (ADR 0032 §1)."""


class ContextUnavailable(Exception):
    """A pinned-``on`` call's pack could not be built and the call cannot fall back; never
    escapes the kernel's two driver call sites."""


def assembled_payload(pack: ContextPack, *, turn: int, acknowledgement: bool) -> dict[str, Any]:
    """The ``context.assembled`` payload: ids, counts, a digest and the kernel's estimates,
    never a value (PR-26)."""
    omitted = [d.ref for d in pack.dropped if d.kind is DroppedKind.OBSERVATION]
    return {
        "turn": turn,
        "acknowledgement": acknowledgement,
        "pack_digest": pack.digest,
        "pack_tokens": layer_tokens(pack),
        "observations": len(pack.observations),
        "dropped": {k.value: sum(d.kind is k for d in pack.dropped) for k in DroppedKind},
        "drop_reasons": {r.value: sum(d.reason is r for d in pack.dropped) for r in DroppedReason},
        "omitted_evidence": omitted,
        "masked_evidence": [o.evidence.evidence_id for o in pack.observations if o.masked],
    }


class ContextOnMixin(ContextShadowMixin):
    async def _context_input(
        self,
        run: RunRecord,
        cont: _Continuation,
        step_input: DriverInput,
        *,
        acknowledgement: bool = False,
    ) -> tuple[RunRecord, DriverInput]:
        """The run (its revision moved by a fallback) and the input for the call about to
        run: with this turn's pack for a run pinned ``on``, unchanged for every other run.
        Raises `RouteRefused` or `ContextUnavailable`. A failure reading the pack's records
        counts as an assembly failure; a store error while deciding the fallback propagates."""
        if self._run_modes(cont).context_assembler is not FeatureMode.ON:
            return run, step_input
        self._check_route(cont)  # a refused route assembles nothing and never falls back
        turn = cont.turns + 1 if acknowledgement else cont.turns
        try:
            inputs = await self._pack_inputs(run, cont)
            pack = assemble(
                ON_POLICY,
                inputs.ledger,
                tuple(cont.observations.values()),
                dict(cont.read_errors),
                step_input.findings,
                self._registry.data_classes,
                self._route,
                task=inputs.task,
                tool_set=inputs.tool_set,
                turn=turn,
                observation_turns=inputs.observation_turns,
                deferred_pending=cont.pending_action_id is not None,
                referenced_evidence=inputs.referenced,
            )
        except Exception:  # no exception text reaches an event (PR-25, PR-28)
            events = await self._store.list_events(run.tenant_id, run.run_id)
            reserved = any(e.type is RunEventType.ACTION_RESERVED for e in events)
            if reserved or not unmasked_allowed(self._route):
                raise ContextUnavailable from None
            run = await self._store.get_run(run.tenant_id, run.run_id)
            run = await self.record_fallback(
                run, "context_assembler", ReasonCode.CONTEXT_ASSEMBLY_FAILED
            )
            return run, step_input
        return run, dataclasses.replace(step_input, context=pack)

    async def _record_context_assembled(
        self,
        run: RunRecord,
        cont: _Continuation,
        step_input: DriverInput,
        *,
        acknowledgement: bool = False,
    ) -> RunRecord:
        """Append the turn's ``context.assembled`` after the driver returned, when the call
        carried a pack; only the run revision moves."""
        pack = step_input.context
        if pack is None:
            return run
        ack = acknowledgement
        turn = cont.turns + 1 if ack else cont.turns
        event = (
            RunEventType.CONTEXT_ASSEMBLED,
            assembled_payload(pack, turn=turn, acknowledgement=ack),
            None,
        )
        run = await self._store.get_run(run.tenant_id, run.run_id)
        return await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}), run.revision, [event]
        )
