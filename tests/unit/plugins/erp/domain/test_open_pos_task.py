"""The read-only ERP task definition ``open-pos`` (ADR 0033 §3, Task 3e.2, owner G2 answer 5).

The Phase 3 live check binds "List the open purchase orders" to it with
``grounded_answers: on``, so ``grounded.answer.v1`` ends the run ``GROUNDED`` with no bespoke
answer contract. It names read capabilities only and sets ``grounded_answer``; its tool set
holds no typed answer, so a run bound to it in ``execution_ir: on`` admits the generic
answer. Checked here on the simulator: the kernel suite imports no plugin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from e_agent.contracts.capability import EffectKind, Risk
from e_agent.contracts.context import TaskContext
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.grounding import Citation
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.contracts.task import GROUNDED_ANSWER, AcceptanceSpec
from e_agent.kernel.registry import PluginRegistry
from e_agent.plugins.erp.domain import plugin
from e_agent.plugins.erp.domain.testing.scripted_tasks import TASK_KINDS, ScriptedErpDriver
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.sdk.ports import DriverInput, DriverStep, ProposeAction, ReadRequest, RequestReads
from e_agent.server.bootstrap import Runtime, build_runtime
from e_agent.server.profile import Profile, load_profile

OPEN_POS = "open-pos"
CONN = "conn-fixture-erp"
RFQ_READ = "procurement.draft-rfq.read.v1"
OPEN_POS_CAPABILITIES = (
    "procurement.draft-rfq.read.v1",
    "procurement.open-demands.read.v1",
    "procurement.demand.read.v1",
    "procurement.offers.read.v1",
    "inventory.availability.read.v1",
)


@dataclass
class RfqDriver:
    """Reads draft RFQ rfq:po-100, then answers with ``grounded.answer.v1`` citing its
    state."""

    driver_id: str = "open-pos-grounded-driver"
    seen: list[DriverInput] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.seen.append(step_input)
        if not step_input.observations:
            request = ReadRequest(
                request_id="r1",
                contract_id=RFQ_READ,
                connection_id=CONN,
                arguments={"purchase_order_ref": "rfq:po-100"},
            )
            return RequestReads(reads=(request,))
        obs = step_input.observations[0]
        cited = Citation(
            evidence_id=obs.evidence.evidence_id, pointer="/state", value=obs.data["state"]
        )
        proposal = ActionProposal(
            contract_id=GROUNDED_ANSWER,
            connection_id=CONN,
            arguments={"summary": f"Draft RFQ rfq:po-100 is {obs.data['state']}."},
            citations=(cited,),
        )
        return ProposeAction(proposal=proposal)


def _profile(features: Features) -> Profile:
    profile = load_profile(fixture_profile_path())
    return profile.model_copy(update={"features": features})


async def _runtime(features: Features) -> Runtime:
    # The CLI path: `--task open-pos` with a non-scripted driver (3e.2 review R1-2).
    return await build_runtime(
        _profile(features), driver_factory=lambda _registry: RfqDriver(), task_kind=OPEN_POS
    )


def _read_only(registry: PluginRegistry, capabilities: tuple[str, ...]) -> None:
    for contract_id in capabilities:
        descriptor = registry.descriptor(contract_id)
        assert descriptor.effect is EffectKind.READ, contract_id
        assert descriptor.risk is Risk.READ, contract_id
        assert descriptor.agent_visible, contract_id


async def test_open_pos_is_read_only_and_admits_grounded_answer() -> None:
    definitions = {d.task_id: d for d in plugin.load_task_definitions()}
    assert OPEN_POS in definitions
    declared = [(t.task_id, t.version) for t in plugin.load_manifest().provides_task_definitions]
    assert (OPEN_POS, "1") in declared

    on = Features(execution_ir=FeatureMode.ON, grounded_answers=FeatureMode.ON)
    rt = await _runtime(on)
    task = rt.registry.task_definitions[OPEN_POS]
    assert task.capabilities == OPEN_POS_CAPABILITIES
    _read_only(rt.registry, task.capabilities)
    assert task.acceptance == AcceptanceSpec(grounded_answer=True)
    assert task.budgets is not None and task.budgets.max_admitted_writes == 0

    run = await rt.coordinator.start_run(
        rt.operator, task.goal_template, rt.scope, task_kind=OPEN_POS
    )

    assert run.task_id == OPEN_POS
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.GROUNDED), run.reason
    events = await rt.store.list_events(rt.operator.tenant_id, run.run_id)
    (final,) = [e for e in events if e.type is RunEventType.MESSAGE_FINAL]
    assert final.payload["contract_id"] == GROUNDED_ANSWER
    assert [c["pointer"] for c in final.payload["citations"]] == ["/state"]
    assert not [e for e in events if e.type is RunEventType.OUTCOME_REPORTED]
    assert await rt.store.list_actions(rt.operator.tenant_id, run.run_id) == []
    cont = await rt.coordinator._load_cont(rt.operator.tenant_id, run.run_id)
    assert rt.coordinator._admits_grounded_answer(run, cont)
    print(f"open-pos: {len(task.capabilities)} read capabilities, grounded end")


async def test_open_pos_does_not_admit_grounded_answer_unless_pinned_on() -> None:
    """``shadow`` and ``off`` never admit it, whatever the definition says."""
    cases = 0
    for mode in (FeatureMode.OFF, FeatureMode.SHADOW):
        rt = await _runtime(Features(execution_ir=FeatureMode.ON, grounded_answers=mode))
        run = await rt.coordinator.start_run(rt.operator, "q", rt.scope, task_kind=OPEN_POS)
        assert run.reason_code is not ReasonCode.GROUNDED
        cont = await rt.coordinator._load_cont(rt.operator.tenant_id, run.run_id)
        assert not rt.coordinator._admits_grounded_answer(run, cont)
        cases += 1
    assert cases == 2


def _grounded_flag(definitions: Any) -> list[str]:
    return sorted(d.task_id for d in definitions if d.acceptance.grounded_answer)


def test_only_open_pos_sets_grounded_answer() -> None:
    assert _grounded_flag(plugin.load_task_definitions()) == [OPEN_POS]


async def test_open_pos_is_a_preset_the_scripted_driver_refuses() -> None:
    """open-pos is a preset, so `--task open-pos` reaches a model driver through the server
    path; the scripted driver has no scenario for it and refuses it when the runtime is
    built, before any run (3e.2 review R1-2), and model qualification does not offer it."""
    assert OPEN_POS in {p.kind for p in plugin.TASK_PRESETS}
    assert OPEN_POS not in TASK_KINDS
    with pytest.raises(ValueError, match="no scenario for task kind 'open-pos'"):
        ScriptedErpDriver(connection_id=CONN, task_kind=OPEN_POS)
    profile = load_profile(fixture_profile_path())
    with pytest.raises(ValueError, match="no scenario for task kind 'open-pos'"):
        await build_runtime(profile, task_kind=OPEN_POS)
    rt = await _runtime(Features())  # the server path with a non-scripted driver
    assert (
        rt.registry.task_presets[OPEN_POS].prompt
        == rt.registry.task_definitions[OPEN_POS].goal_template
    )
