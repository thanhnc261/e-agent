"""ERP task definitions (ADR 0028) and effect declarations (ADR 0029), Task 2c.2."""

from __future__ import annotations

import json
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest
from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.capability import EffectKind, Idempotency, Reversibility, Risk
from e_agent.contracts.common import format_decimal
from e_agent.contracts.context import Budgets, Principal, TaskContext
from e_agent.contracts.outcome import OutcomeStatus
from e_agent.contracts.task import AnswerCondition, answer_condition_met
from e_agent.kernel.connections import ConnectionCatalog
from e_agent.kernel.registry import PluginRegistry
from e_agent.plugins.erp.domain import plugin
from e_agent.plugins.erp.domain.procurement import SHORTAGE_ANSWER
from e_agent.plugins.erp.domain.procurement.answers import ShortageAnswerVerifier
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.plugins.erp.simulator.fake_erp import FakeErp
from e_agent.plugins.erp.simulator.scenarios import SCENARIOS
from e_agent.sdk.discovery import artifact_digest, discover
from e_agent.sdk.manifest import PluginManifest
from e_agent.sdk.ports import ReadRequest
from e_agent.server.bootstrap import admit_plugins, tool_specs
from e_agent.server.profile import Profile, load_profile

REPO = Path(__file__).resolve().parents[5]
GOLDEN = Path(__file__).parent / "golden" / "task_capabilities.json"
LIVE_EXAMPLE = REPO / "profiles" / "live.example.json"
ODOO_MANIFEST = REPO / "src" / "e_agent" / "plugins" / "erp" / "odoo" / "e_agent_plugin.json"
ERP_KINDS = (
    "draft-po",
    "shortage",
    "recommend",
    "amend-rfq",
    "quotation",
    "late-orders",
    "crm-lead",
    "overdue-invoices",
)
ASSISTANT = "assistant"
OPEN_POS = "open-pos"
"""The read-only grounded-answer definition of Phase 3 (Task 3e.2). The Phase 2 golden
predates it, so its capabilities are pinned in `test_open_pos_task.py` instead."""

# Chosen per target §6.4.2; the report of Task 2c.2 justifies each value.
EXPECTED_WRITE_EFFECTS = {
    "procurement.purchase-order.create-draft.v1": (Risk.WRITE_LOW, Reversibility.IRREVERSIBLE),
    "procurement.draft-rfq.amend.v1": (Risk.WRITE_HIGH, Reversibility.IRREVERSIBLE),
    "sales.quotation.create-draft.v1": (Risk.WRITE_LOW, Reversibility.IRREVERSIBLE),
    "crm.lead.create.v1": (Risk.WRITE_HIGH, Reversibility.IRREVERSIBLE),
}


def _admit(profile: Profile) -> PluginRegistry:
    registry, _ = admit_plugins(profile, ConnectionCatalog(profile.connections), discover(), None)
    return registry


def _fixture() -> tuple[Profile, PluginRegistry]:
    profile = load_profile(fixture_profile_path())
    return profile, _admit(profile)


def _pinned_live() -> Profile:
    data: dict[str, Any] = load_profile(LIVE_EXAMPLE).model_dump(mode="json")
    found = {p.manifest.plugin_id: p for p in discover()}
    for pid, cfg in data["enabled_plugins"].items():
        cfg["artifact_sha256"] = artifact_digest(found[pid].artifact_files)
    return Profile.model_validate(data)


def test_task_definitions_load_from_resources() -> None:
    root = files("e_agent.plugins.erp.domain").joinpath("tasks")
    for task_id in (*ERP_KINDS, ASSISTANT, OPEN_POS):
        resource = json.loads(root.joinpath(f"{task_id}.json").read_text("utf-8"))
        assert resource["task_id"] == task_id
    definitions = plugin.load_task_definitions()
    assert tuple(d.task_id for d in definitions) == (*ERP_KINDS, ASSISTANT, OPEN_POS)
    manifest = plugin.load_manifest()
    assert [(t.task_id, t.version) for t in manifest.provides_task_definitions] == [
        (d.task_id, d.version) for d in definitions
    ]
    # One catalogue: each preset is its definition's projection (D8: task_id is the kind).
    by_id = {d.task_id: d for d in definitions}
    assert tuple(p.kind for p in plugin.TASK_PRESETS) == ERP_KINDS  # open-pos has none
    for preset in plugin.TASK_PRESETS:
        definition = by_id[preset.kind]
        assert preset.prompt == definition.goal_template
        assert preset.help == definition.title
        assert dict(preset.default_refs) == plugin.TASK_REFS
    contribution = plugin.create_plugin(_services())
    assert contribution.task_definitions == definitions


def _services() -> Any:
    from e_agent.sdk.ports import PluginServices

    return PluginServices(settings={})


def test_task_capabilities_match_golden() -> None:
    golden = json.loads(GOLDEN.read_text("utf-8"))
    profile, registry = _fixture()
    today = sorted(spec.contract_id for spec in tool_specs(registry, profile))
    assert today, "today's tool set is empty"
    assert golden["today"] == today
    chosen = {tid: sorted(d.capabilities) for tid, d in registry.task_definitions.items()}
    phase3 = {OPEN_POS: chosen.pop(OPEN_POS)}  # pinned in test_open_pos_task.py
    assert chosen == golden["definitions"]
    cases = 0
    for task_id, capabilities in sorted({**chosen, **phase3}.items()):
        outside = sorted(set(capabilities) - set(today))
        assert not outside, f"{task_id} names capabilities outside today's set: {outside}"
        cases += 1
    print(f"task capability subsets checked: {cases}")
    assert cases == len(ERP_KINDS) + 2


def test_assistant_definition_is_read_only() -> None:
    _, registry = _fixture()
    assistant = registry.task_definitions[ASSISTANT]
    effects = {registry.descriptor(cid).effect for cid in assistant.capabilities}
    assert EffectKind.WRITE not in effects
    assert all(registry.descriptor(cid).risk is Risk.READ for cid in assistant.capabilities)
    assert assistant.acceptance.required_effects == ()
    assert assistant.budgets is not None
    assert assistant.budgets.model_fields_set == {"max_admitted_writes"}
    assert assistant.budgets.max_admitted_writes == 0


def test_answer_definitions_admit_no_writes() -> None:
    _, registry = _fixture()
    for task_id in ("shortage", "recommend", "late-orders", "overdue-invoices"):
        definition = registry.task_definitions[task_id]
        assert definition.acceptance.required_answer is not None
        assert definition.budgets == Budgets(max_admitted_writes=0)
        assert all(
            registry.descriptor(cid).effect is not EffectKind.WRITE
            for cid in definition.capabilities
        )


def test_write_definitions_require_their_verified_effect() -> None:
    _, registry = _fixture()
    for task_id in ("draft-po", "amend-rfq", "quotation", "crm-lead"):
        definition = registry.task_definitions[task_id]
        [required] = definition.acceptance.required_effects
        assert registry.descriptor(required.contract_id).effect is EffectKind.WRITE
        assert required.min_verified == 1
        assert definition.budgets is None
    # Only draft-po has a verified no-op outcome; the other writes require their effect.
    for task_id in ("amend-rfq", "quotation", "crm-lead"):
        assert registry.task_definitions[task_id].acceptance.required_answer is None


def test_draft_po_acceptance_allows_verified_no_op_answer() -> None:
    # Target §1.3: "a verified draft PO or a verified no-op". The no-op is the verified
    # zero-shortage answer the scripted driver gives when nothing is to be ordered.
    _, registry = _fixture()
    acceptance = registry.task_definitions["draft-po"].acceptance
    assert [e.contract_id for e in acceptance.required_effects] == [
        "procurement.purchase-order.create-draft.v1"
    ]
    assert acceptance.required_answer == "procurement.shortage.answer.v1"
    assert registry.descriptor(acceptance.required_answer).effect is EffectKind.ANSWER


CTX = TaskContext(
    run_id="run_1",
    tenant_id="t",
    principal=Principal(principal_id="p", tenant_id="t", roles=frozenset()),
    resource_scope=frozenset({"c"}),
)


class _Reader:
    """The host's scoped reader over the simulator, for the verifier's fresh reads."""

    def __init__(self, erp: FakeErp) -> None:
        self.erp = erp

    async def read(self, contract_id, arguments):  # type: ignore[no-untyped-def]
        request = ReadRequest("v", contract_id, "c", arguments)
        return await self.erp.read(CTX, None, request)  # type: ignore[arg-type]


def _shortage_answer(shortage: str, available: str) -> ActionRecord:
    return ActionRecord(
        action_id="act_1",
        tenant_id="t",
        run_id="run_1",
        logical_operation_id="op_1",
        contract_id=SHORTAGE_ANSWER,
        binding_id="b",
        connection_id="c",
        connection_version=1,
        credential_subject="c@1/s",
        arguments={
            "demand_ref": "demand:d-001",
            "product_ref": "product:widget-a",
            "demand_quantity": "12",
            "available": available,
            "inbound": "0",
            "shortage": shortage,
        },
        digest="d1",
        state=ActionState.COMMITTED,
        revision=1,
    )


@pytest.mark.asyncio
async def test_draft_po_acceptance_answer_is_zero_shortage() -> None:
    """The no-op alternative is the verified zero-shortage answer only: an accurate answer
    reporting a positive shortage verifies, yet leaves draft-po unmet (Codex review C-2)."""
    _, registry = _fixture()
    acceptance = registry.task_definitions["draft-po"].acceptance
    assert acceptance.required_answer == SHORTAGE_ANSWER
    assert acceptance.answer_condition == AnswerCondition(check="shortage", expected="0")
    # The verifier's `expected` is `format_decimal` of the computed shortage.
    for zero in (
        Decimal(12) - Decimal(12) - Decimal(0),
        max(Decimal(-3), Decimal(0)),
        Decimal("0E+2"),
    ):
        assert format_decimal(zero) == "0"
    verifier = ShortageAnswerVerifier()
    none_short = await verifier.verify(
        CTX, _shortage_answer("0", "12"), None, _Reader(FakeErp(SCENARIOS["zero-shortage"]))
    )
    assert none_short.status is OutcomeStatus.VERIFIED
    assert answer_condition_met(acceptance, none_short)
    short = await verifier.verify(
        CTX, _shortage_answer("7", "5"), None, _Reader(FakeErp(SCENARIOS["valid"]))
    )
    assert short.status is OutcomeStatus.VERIFIED  # an accurate answer for the shortage task
    assert not answer_condition_met(acceptance, short)
    # The shortage task keeps accepting any verified answer, a positive shortage included.
    shortage_task = registry.task_definitions["shortage"].acceptance
    assert shortage_task.answer_condition is None
    assert answer_condition_met(shortage_task, short)


def test_erp_write_capabilities_declare_effects() -> None:
    writes = {
        c.contract_id: c
        for c in plugin.load_manifest().provides_capabilities
        if c.effect is EffectKind.WRITE
    }
    assert set(writes) == set(EXPECTED_WRITE_EFFECTS)
    for contract_id, (risk, reversibility) in EXPECTED_WRITE_EFFECTS.items():
        cap = writes[contract_id]
        assert {"risk", "reversibility"} <= cap.model_fields_set, contract_id
        assert (cap.risk, cap.reversibility) == (risk, reversibility)
    odoo = PluginManifest.model_validate(json.loads(ODOO_MANIFEST.read_text("utf-8")))
    write_bindings = [b for b in odoo.provides_bindings if b.contract_id in writes]
    assert len(write_bindings) == len(writes)
    for binding in write_bindings:
        assert "idempotency" in binding.model_fields_set, binding.binding_id
        assert binding.idempotency is Idempotency.PROVIDER_KEY
    # The live example profile admits with no defaulted write declaration.
    registry = _admit(_pinned_live())
    assert registry.report.defaulted_declarations == []
    for binding in registry.bindings:
        if binding.contract_id in writes:
            assert binding.idempotency is Idempotency.PROVIDER_KEY


def test_fixture_profile_reports_simulator_defaults() -> None:
    # The simulator's write bindings keep the default idempotency; a fixture profile
    # accepts them and reports each one in the admission report (ADR 0029).
    _, registry = _fixture()
    reported = {
        (d.plugin_id, d.subject_id, d.fields) for d in registry.report.defaulted_declarations
    }
    assert reported == {
        ("fixture-erp", "fixture-erp.procurement.po-create", ("idempotency",)),
        ("fixture-erp", "fixture-erp.procurement.rfq-amend", ("idempotency",)),
        ("fixture-erp", "fixture-erp.sales.quotation-create", ("idempotency",)),
        ("fixture-erp", "fixture-erp.crm.lead-create", ("idempotency",)),
    }


async def test_every_scripted_kind_has_a_scenario() -> None:
    """No preset can crash the fixture driver (3e.2 review R1-2): every preset kind is one the
    scripted driver has a scenario for, a fixture run of each leaves RUNNING, and every
    definition without a preset is an unscripted one."""
    from e_agent.contracts.run import RunState
    from e_agent.plugins.erp.domain.testing.scripted_tasks import TASK_KINDS, ScriptedErpDriver
    from e_agent.server.bootstrap import build_runtime

    kinds = {p.kind for p in plugin.TASK_PRESETS}
    assert kinds == set(TASK_KINDS) == set(ERP_KINDS)
    definitions = {d.task_id for d in plugin.load_task_definitions()}
    assert definitions - kinds == plugin.UNSCRIPTED_TASKS == {ASSISTANT, OPEN_POS}
    cases = 0
    for kind in sorted(kinds):
        assert ScriptedErpDriver.handles(kind), kind
        rt = await build_runtime(load_profile(fixture_profile_path()), task_kind=kind)
        run = await rt.coordinator.start_run(rt.operator, kind, rt.scope, task_kind=kind)
        assert run.state is not RunState.RUNNING, (kind, run.state)
        cases += 1
    for kind in plugin.UNSCRIPTED_TASKS:
        assert not ScriptedErpDriver.handles(kind), kind
    print(f"scripted kinds with a scenario: {cases}")
    assert cases == len(ERP_KINDS)
