"""``features.context_assembler: on`` (ADR 0032 §7, Task 3d.5, Review Focus 4 and 7).

Every driver call of a run pinned ``on`` (each run-loop turn and the post-write
acknowledgement turn) passes the turn's pack in ``DriverInput.context``, built by `assemble`
from the same records ``shadow`` reads (`_pack_inputs`). After the call the kernel records
``context.assembled``: the turn, the pack digest, counts and the drop log, never a value
(PR-26). It marks the turn as ``context.compared`` does in shadow, so a read's age for
clearing comes from the events (`observation_turns`), and it is the durable record of the
pack digests and drop log ADR 0032 §13 names. A turn that fell back records it too, with
``fallback: true`` and no pack keys, so ages stay exact (review D3-52, D3-51).

The drop log keeps each ``Dropped`` as (kind, ref, reason). A ref into observation data is
cut at the first token no class declaration names literally; an index into a list the data
holds is kept, a numeric dict key is not (review D3-71): a key no declaration names may be
data (review D3-12), so the log never names one, whatever the route. Other refs (evidence
ids, ``finding:<n>#/…``, ``read_error:<id>``) are kernel ids.

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
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from e_agent.contracts import data_classes as dc
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


def _named_paths(classes: Mapping[str, dc.DataClass]) -> frozenset[dc.Path]:
    """Every declaration key's tokens and their prefixes: the property names a declaration
    writes literally."""
    parsed = [dc.parse_pointer(key) for key in classes]
    return frozenset(tokens[:end] for tokens in parsed for end in range(1, len(tokens) + 1))


Named = Mapping[str, tuple[frozenset[dc.Path], Any]]
"""Per evidence id of the run: the property names its declarations write (`_named_paths`)
and the observation's data, whose structure says whether a token indexes a list."""


def safe_ref(ref: str, named: Named) -> str:
    """``ref`` as the drop log records it. A pointer into an observation (its evidence id in
    ``named``) is walked through the observation's data and cut before the first token that
    is neither a list index nor a dict key some declaration names; any other ref is kept. A
    numeric token is a list index only where the data holds a list: a numeric dict key is
    data like any other key (review D3-71)."""
    evidence, sep, pointer = ref.partition("#")
    if not sep or evidence not in named:
        return ref
    names, node = named[evidence]
    path: dc.Path = ("output",)
    kept: list[str] = []
    for token in dc.parse_pointer(pointer) if pointer else ():
        if isinstance(node, list):
            if dc.instance_token(token) != dc.ITEMS or int(token) >= len(node):
                break
            child: dc.Path = (*path, dc.ITEMS)
            node = node[int(token)]
        elif isinstance(node, Mapping):
            child = (*path, token)  # a key ``items`` is never the array marker (D3-81)
            if token == dc.ITEMS or child not in names or token not in node:
                break
            node = node[token]
        else:
            break
        kept.append(token)
        path = child
    return f"{evidence}#{dc.format_pointer(kept)}"


def drop_log(pack: ContextPack, named: Named) -> list[dict[str, str]]:
    return [
        {"kind": d.kind.value, "ref": safe_ref(d.ref, named), "reason": d.reason.value}
        for d in pack.dropped
    ]


def assembled_payload(
    pack: ContextPack | None,
    *,
    turn: int,
    acknowledgement: bool,
    named: Named = MappingProxyType({}),
) -> dict[str, Any]:
    """The ``context.assembled`` payload: ids, counts, a digest, the kernel's estimates and
    the drop log, never a value (PR-26). A fallback turn (no pack) records its turn only."""
    if pack is None:
        return {"turn": turn, "acknowledgement": acknowledgement, "fallback": True}
    omitted = [d.ref for d in pack.dropped if d.kind is DroppedKind.OBSERVATION]
    return {
        "turn": turn,
        "acknowledgement": acknowledgement,
        "fallback": False,
        "pack_digest": pack.digest,
        "pack_tokens": layer_tokens(pack),
        "observations": len(pack.observations),
        "dropped": {k.value: sum(d.kind is k for d in pack.dropped) for k in DroppedKind},
        "drop_reasons": {r.value: sum(d.reason is r for d in pack.dropped) for r in DroppedReason},
        "omitted_evidence": omitted,
        "masked_evidence": [o.evidence.evidence_id for o in pack.observations if o.masked],
        "drop_log": drop_log(pack, named),
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
        """Append the turn's ``context.assembled`` after the driver returned, for a run
        pinned ``on``: with the pack's record, or ``fallback: true`` when the call fell back;
        only the run revision moves."""
        if self._run_modes(cont).context_assembler is not FeatureMode.ON:
            return run
        pack = step_input.context
        named = {
            o.evidence.evidence_id: (
                _named_paths(self._registry.data_classes(o.contract_id)),
                o.data,
            )
            for o in cont.observations.values()
        }
        ack = acknowledgement
        turn = cont.turns + 1 if ack else cont.turns
        payload = assembled_payload(pack, turn=turn, acknowledgement=ack, named=named)
        event = (RunEventType.CONTEXT_ASSEMBLED, payload, None)
        run = await self._store.get_run(run.tenant_id, run.run_id)
        return await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}), run.revision, [event]
        )
