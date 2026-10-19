"""The generic grounded answer ``grounded.answer.v1`` (ADR 0033 §3, §5, plan D5, Task 3e.2).

A core answer owned by the kernel, for a read-only question no typed answer contract covers:
arguments ``{summary}`` and at least one citation in the kernel envelope
(`ActionProposal.citations`). It is not a registry capability: it reads and writes nothing,
has no connection, binding or verifier (a connection named on it is ignored, PR-12), and
creates no `ActionRecord`.

**Where.** `ProposalsMixin._handle_proposal` hands it here before the task-set check and the
capability lookup, and only in a run pinned ``grounded_answers: on`` (`_grounded_branch`,
`_run_modes`). In ``off`` and ``shadow`` the call takes today's path (``KERNEL-PROPOSAL-KIND``,
or ``KERNEL-PLAN-CAPABILITY`` on a bound ``execution_ir: on`` run): ``shadow`` acts on
nothing (ADR 0027).

**Admission** (`_admits_grounded_answer`), fixed for the run because its pinned mode, tool
set and task definition are: the run is pinned ``on``; it is unbound, or bound to an admitted
definition snapshot whose acceptance spec sets ``grounded_answer`` (a bound run without its
snapshot admits nothing); and its offered tool set (the snapshot's capabilities, else every
agent-visible capability) holds no typed answer (``EffectKind.ANSWER``), so where a typed
answer exists its verifier decides (PR-19). A call the run does not admit is the fixed repair
finding ``KERNEL-GROUNDED-ANSWER`` (`_repair_finding`: recorded in ``validation.completed``
with no action id, within ``max_validation_repairs``).

**The offer** (`_grounding_offer`, Task 3e.4). Every run-loop driver call carries
``DriverInput.grounding``, derived from the same pin and predicate, never the profile (D8):
pinned ``off`` is ``off`` (the input is today's, byte for byte), ``shadow`` is ``cite``, and
``on`` is ``cite_and_answer`` when the run admits the generic answer, ``cite`` otherwise. The
post-write acknowledgement turn keeps ``off``: the kernel takes only its final text.

**The check.** Arguments other than one non-empty ``summary`` are ``KERNEL-ARGS``, no citation
is ``KERNEL-CITATION``, and the citations are checked by `check_citations` against this run's
continuation, through the class view the model was shown when the run is pinned
``context_assembler: on`` (`ClassView`, 3e.1 R1-1): one that does not resolve is
``KERNEL-CITATION``. When every citation resolves, the kernel writes ``message.final`` with the
summary as ``text``, ``contract_id`` and the at-rest citations (evidence id, pointer, value
digest; PR-26), then ends the run ``SUCCEEDED`` with ``GROUNDED`` through `_succeed`, whose
acceptance gate reads that record (ADR 0028 refined). ``GROUNDED`` is never ``verified``: no
outcome report is written.

**Failure.** A check that cannot run fails the run closed with ``GROUNDING_UNAVAILABLE``
before or after a reservation, in reconciliation while one is unresolved (`_end_closed`):
there is no typed verifier to fall back to, so no ``feature.fallback`` is recorded. No event
carries exception text.
"""

from __future__ import annotations

import dataclasses

from e_agent.contracts.capability import EffectKind
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import ReasonCode, RunRecord
from e_agent.contracts.task import GROUNDED_ANSWER
from e_agent.sdk.ports import DriverInput, GroundingOffer

from .at_rest import repair_at_rest
from .continuation import _Continuation
from .grounding import KERNEL_CITATION, ClassView, GroundingMixin, check_citations
from .ir_on import _fixed

KERNEL_GROUNDED_ANSWER = "KERNEL-GROUNDED-ANSWER"
NOT_ADMITTED = (
    "The grounded answer is not available to this run; use its typed answer or its task's tools."
)
"""The fixed message of the ``KERNEL-GROUNDED-ANSWER`` repair finding (no model text)."""
NO_CITATION = "A grounded answer needs at least one citation of a value this run read."
SUMMARY_SHAPE = "The grounded answer takes one non-empty summary."
GROUNDED_REASON = "grounded answer"
"""The run reason of a ``GROUNDED`` end."""


class GroundedAnswerMixin(GroundingMixin):
    def _grounded_branch(self, cont: _Continuation, proposal: ActionProposal) -> bool:
        """Whether `_handle_proposal` hands ``proposal`` to `_handle_grounded_answer`: the
        generic answer in a run pinned ``on``. Every other run keeps today's path."""
        return (
            proposal.contract_id == GROUNDED_ANSWER
            and self._run_modes(cont).grounded_answers is FeatureMode.ON
        )

    def _admits_grounded_answer(self, run: RunRecord, cont: _Continuation) -> bool:
        """ADR 0033 §3's three conditions, from the run's pin and its admitted snapshot,
        never the profile."""
        if self._run_modes(cont).grounded_answers is not FeatureMode.ON:
            return False
        capabilities = self._registry.capabilities
        if run.task_id is not None:
            task = self._on_task(run, cont)
            if task is None or not task.acceptance.grounded_answer:
                return False
            offered = task.capabilities
        else:
            offered = tuple(cid for cid, cap in capabilities.items() if cap.agent_visible)
        return not any(
            cid in capabilities and capabilities[cid].effect is EffectKind.ANSWER for cid in offered
        )

    def _grounding_offer(self, run: RunRecord, cont: _Continuation) -> GroundingOffer:
        """What this run's driver calls offer (ADR 0033 §5), from its pin, never the profile."""
        mode = self._run_modes(cont).grounded_answers
        if mode is FeatureMode.OFF:
            return GroundingOffer.OFF
        if mode is FeatureMode.ON and self._admits_grounded_answer(run, cont):
            return GroundingOffer.CITE_AND_ANSWER
        return GroundingOffer.CITE

    def _with_grounding(
        self, run: RunRecord, cont: _Continuation, step_input: DriverInput
    ) -> DriverInput:
        """``step_input`` carrying the run's offer; unchanged for a run pinned ``off``."""
        offer = self._grounding_offer(run, cont)
        if offer is GroundingOffer.OFF:
            return step_input
        return dataclasses.replace(step_input, grounding=offer)

    async def _handle_grounded_answer(
        self, run: RunRecord, cont: _Continuation, proposal: ActionProposal
    ) -> RunRecord | DriverInput:
        if not self._admits_grounded_answer(run, cont):
            finding = _fixed(KERNEL_GROUNDED_ANSWER, NOT_ADMITTED)
            return await self._repair_finding(run, cont, (finding,))
        summary = proposal.arguments.get("summary")
        if set(proposal.arguments) != {"summary"} or not (
            isinstance(summary, str) and summary.strip()
        ):
            return await self._repair_finding(run, cont, (_fixed("KERNEL-ARGS", SUMMARY_SHAPE),))
        if not proposal.citations:
            return await self._repair_finding(run, cont, (_fixed(KERNEL_CITATION, NO_CITATION),))
        try:
            view = None
            if self._run_modes(cont).context_assembler is FeatureMode.ON:  # what the pack showed
                view = ClassView(self._registry.data_classes, self._route)
            result = check_citations(cont.observations.values(), proposal.citations, view)
        except Exception:  # no fallback, no exception text (ADR 0033 §5, PR-25, PR-28)
            return await self._end_closed(run, ReasonCode.GROUNDING_UNAVAILABLE)
        if not result.grounded:  # recorded as digests where a citation named nothing (3.R1)
            return await repair_at_rest(self._repair_finding, run, cont, result)
        final = {"text": summary, "contract_id": GROUNDED_ANSWER, "citations": result.at_rest()}
        run = await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [(RunEventType.MESSAGE_FINAL, final, None)],
        )
        return await self._succeed(run, cont, GROUNDED_REASON, ReasonCode.GROUNDED)
