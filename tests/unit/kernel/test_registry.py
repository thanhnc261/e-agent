"""Registry admission and binding resolution (MVP design §6, §13)."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from e_agent.contracts.capability import CapabilityDescriptor, EffectKind, Idempotency
from e_agent.contracts.context import Budgets
from e_agent.contracts.task import TaskDefinition
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.registry import DefaultedDeclaration, EnabledPlugin, PluginRegistry
from e_agent.sdk.discovery import discover
from e_agent.sdk.manifest import BindingTemplate, TaskDeclaration
from e_agent.sdk.ports import DriverRequest, PluginContribution, TaskPreset

from .conftest import BINDINGS, CREATE, NOTES_TASK, READ


def _registry(**connections: tuple[str, ...]) -> PluginRegistry:
    reg = PluginRegistry(connections or {"notes-mem.read": ("c1",)})
    reg.register(
        plugin_id="notes-fixture",
        plugin_version="1",
        declared_capabilities=(READ, CREATE),
        binding_templates=BINDINGS,
        contribution=PluginContribution(capabilities=(READ, CREATE)),
    )
    return reg


def test_conflicting_capability_definitions_rejected() -> None:
    reg = _registry()
    other = CapabilityDescriptor(
        contract_id=READ.contract_id,
        effect=EffectKind.WRITE,
        input_schema_id="x",
        output_schema_id="y",
    )
    with pytest.raises(KernelError) as err:
        reg.register(
            plugin_id="other",
            plugin_version="1",
            declared_capabilities=(other,),
            binding_templates=(),
            contribution=PluginContribution(capabilities=(other,)),
        )
    assert err.value.code is ErrorCode.STARTUP_REJECTED


def test_duplicate_binding_id_rejected() -> None:
    reg = _registry()
    with pytest.raises(KernelError):
        reg.register(
            plugin_id="other",
            plugin_version="1",
            declared_capabilities=(),
            binding_templates=(
                BindingTemplate(binding_id="notes-mem.read", contract_id=READ.contract_id),
            ),
            contribution=PluginContribution(),
        )


def test_contribution_must_match_manifest() -> None:
    reg = PluginRegistry({})
    with pytest.raises(KernelError):
        reg.register(
            plugin_id="p",
            plugin_version="1",
            declared_capabilities=(READ,),
            binding_templates=(),
            contribution=PluginContribution(capabilities=()),
        )


def test_two_connections_resolve_and_ambiguity_is_refused() -> None:
    reg = _registry(**{"notes-mem.read": ("c1", "c2")})
    assert reg.resolve(READ.contract_id, "c1").connection_id == "c1"
    assert reg.resolve(READ.contract_id, "c2").connection_id == "c2"
    with pytest.raises(KernelError) as err:
        reg.resolve(READ.contract_id, "c3")
    assert err.value.code is ErrorCode.FORBIDDEN
    reg2 = PluginRegistry({"notes-mem.read": ("c1",), "other-impl.read": ("c1",)})
    reg2.register(
        plugin_id="a",
        plugin_version="1",
        declared_capabilities=(READ, CREATE),
        binding_templates=BINDINGS,
        contribution=PluginContribution(capabilities=(READ, CREATE)),
    )
    reg2.register(
        plugin_id="b",
        plugin_version="1",
        declared_capabilities=(),
        binding_templates=(
            BindingTemplate(binding_id="other-impl.read", contract_id=READ.contract_id),
        ),
        contribution=PluginContribution(),
    )
    with pytest.raises(KernelError) as amb:
        reg2.resolve(READ.contract_id, "c1")
    assert amb.value.code is ErrorCode.CONFLICT


# --- admission through discovery (no import for disabled plugins) ----------------


def _install(root: Path, version: str = "0.3.0", sdk_api: str = ">=1.0,<2.0") -> Path:
    pkg = root / "notes_fixture"
    pkg.mkdir(parents=True)
    marker = root / "IMPORTED"
    (pkg / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n"
    )
    (pkg / "plugin.py").write_text(
        "from e_agent.sdk.ports import PluginContribution\n"
        "def create_plugin(services):\n    return PluginContribution()\n"
    )
    manifest = {
        "plugin_id": "notes-fixture",
        "version": version,
        "sdk_api": sdk_api,
        "factory": "notes_fixture.plugin:create_plugin",
        "kind": "domain",
    }
    (pkg / "e_agent_plugin.json").write_text(json.dumps(manifest))
    info = root / f"notes_fixture-{version}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: notes-fixture\nVersion: {version}\n"
    )
    (info / "entry_points.txt").write_text(
        "[e_agent.plugins.v1]\nnotes = notes_fixture.plugin:create_plugin\n"
    )
    (info / "RECORD").write_text(
        "notes_fixture/__init__.py,,\nnotes_fixture/plugin.py,,\n"
        "notes_fixture/e_agent_plugin.json,,\n"
    )
    return marker


def test_disabled_plugin_is_never_imported(tmp_path: Path) -> None:
    marker = _install(tmp_path)
    reg = PluginRegistry({})
    report = reg.admit(discover([str(tmp_path)]), enabled={})
    assert report.skipped == ["notes-fixture"]
    assert not marker.exists()


def test_enabled_but_missing_plugin_fails_startup(tmp_path: Path) -> None:
    with pytest.raises(KernelError):
        PluginRegistry({}).admit(discover([str(tmp_path)]), {"ghost": EnabledPlugin("1.0")})


def test_version_mismatch_rejected_before_import(tmp_path: Path) -> None:
    marker = _install(tmp_path)
    with pytest.raises(KernelError):
        PluginRegistry({}).admit(
            discover([str(tmp_path)]), {"notes-fixture": EnabledPlugin("9.9.9")}
        )
    assert not marker.exists()


def test_incompatible_sdk_rejected_before_import(tmp_path: Path) -> None:
    marker = _install(tmp_path, sdk_api=">=2.0,<3.0")
    with pytest.raises(KernelError):
        PluginRegistry({}).admit(
            discover([str(tmp_path)]), {"notes-fixture": EnabledPlugin("0.3.0")}
        )
    assert not marker.exists()


def test_manifest_digest_must_match_inventory(tmp_path: Path) -> None:
    marker = _install(tmp_path)
    with pytest.raises(KernelError):
        PluginRegistry({}).admit(
            discover([str(tmp_path)]),
            {"notes-fixture": EnabledPlugin("0.3.0", manifest_sha256="0" * 64)},
        )
    assert not marker.exists()


def test_artifact_bytes_are_checked_before_import(tmp_path: Path) -> None:
    from e_agent.sdk.discovery import artifact_digest

    marker = _install(tmp_path)
    [plugin] = discover([str(tmp_path)])
    pin = artifact_digest(plugin.artifact_files)
    factory = plugin.manifest.factory.split(":")[0].split(".")
    source = tmp_path.joinpath(*factory).with_suffix(".py")
    assert source.exists()
    source.write_text(source.read_text() + "\n# changed after build inventory approval\n")
    with pytest.raises(KernelError, match="artifact bytes differ"):
        PluginRegistry({}).admit(
            [plugin],
            {
                "notes-fixture": EnabledPlugin("0.3.0", artifact_sha256=pin),
            },
        )
    assert not marker.exists()


def test_conflicting_task_presets_rejected() -> None:
    def register(reg: PluginRegistry, plugin_id: str, prompt: str) -> None:
        reg.register(
            plugin_id=plugin_id,
            plugin_version="1",
            declared_capabilities=(),
            binding_templates=(),
            contribution=PluginContribution(
                task_presets=(TaskPreset(kind="notes", prompt=prompt),)
            ),
        )

    reg = PluginRegistry({})
    register(reg, "a", "Summarise the notes.")
    register(reg, "b", "Summarise the notes.")  # the same definition is not a conflict
    with pytest.raises(KernelError) as exc:
        register(reg, "c", "List the notes.")
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    assert reg.task_presets["notes"].prompt == "Summarise the notes."


def test_driver_kind_contributed_twice_rejected() -> None:
    def register(reg: PluginRegistry, plugin_id: str) -> None:
        reg.register(
            plugin_id=plugin_id,
            plugin_version="1",
            declared_capabilities=(),
            binding_templates=(),
            contribution=PluginContribution(driver_factories={"scripted": factory}),
        )

    def factory(request: DriverRequest) -> Any:
        raise AssertionError("never built at registration")

    reg = PluginRegistry({})
    register(reg, "a")
    assert reg.driver_factories == {"scripted": factory}
    # Factories are not comparable definitions, so any second contribution conflicts.
    with pytest.raises(KernelError) as exc:
        register(reg, "b")
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    assert "scripted" in exc.value.safe_message


def test_task_presets_differing_only_in_ref_order_conflict() -> None:
    # Overrides apply in default-ref order, so the order is part of the definition.
    def register(reg: PluginRegistry, plugin_id: str, refs: dict[str, str]) -> None:
        preset = TaskPreset(kind="notes", prompt="customer:acme product:a", default_refs=refs)
        reg.register(
            plugin_id=plugin_id,
            plugin_version="1",
            declared_capabilities=(),
            binding_templates=(),
            contribution=PluginContribution(task_presets=(preset,)),
        )

    reg = PluginRegistry({})
    register(reg, "a", {"customer_ref": "customer:acme", "product_ref": "product:a"})
    with pytest.raises(KernelError) as exc:
        register(reg, "b", {"product_ref": "product:a", "customer_ref": "customer:acme"})
    assert exc.value.code is ErrorCode.STARTUP_REJECTED


# --- declared capability requirements (XA-03, PR-10) ------------------------------

FEATURED = CapabilityDescriptor(
    contract_id="notes.note.search.v1",
    effect=EffectKind.READ,
    input_schema_id="q",
    output_schema_id="n",
    required_features=frozenset({"x"}),
)


def _register_featured(reg: PluginRegistry, supported: frozenset[str]) -> None:
    reg.register(
        plugin_id="notes-fixture",
        plugin_version="1",
        declared_capabilities=(FEATURED,),
        binding_templates=(
            BindingTemplate(
                binding_id="notes-mem.search",
                contract_id=FEATURED.contract_id,
                supported_features=supported,
            ),
        ),
        contribution=PluginContribution(capabilities=(FEATURED,)),
    )


def test_binding_missing_required_feature_refused() -> None:
    reg = PluginRegistry({"notes-mem.search": ("c1",)})
    with pytest.raises(KernelError) as exc:
        _register_featured(reg, frozenset())
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    message = exc.value.safe_message
    assert "notes-mem.search" in message
    assert FEATURED.contract_id in message
    assert "'x'" in message
    assert reg.bindings == []
    assert reg.report.admitted == []


def test_binding_missing_required_feature_refused_without_a_connection() -> None:
    # The template is refused at registration, not only once a connection is assigned.
    with pytest.raises(KernelError) as exc:
        _register_featured(PluginRegistry({}), frozenset({"y"}))
    assert exc.value.code is ErrorCode.STARTUP_REJECTED


def test_binding_with_required_features_admitted() -> None:
    reg = PluginRegistry({"notes-mem.search": ("c1",)})
    _register_featured(reg, frozenset({"x", "y"}))
    binding = reg.resolve(FEATURED.contract_id, "c1")
    assert binding.supported_features == frozenset({"x", "y"})
    assert reg.report.admitted == ["notes-fixture"]


# --- task definitions (ADR 0028) and effect declarations (ADR 0029) ---------------

BOTH_BOUND = {"notes-mem.read": ("c1",), "notes-mem.create": ("c1",)}
DEFAULTED_CREATE = CapabilityDescriptor(
    contract_id="notes.note.archive.v1",
    effect=EffectKind.WRITE,
    input_schema_id="a",
    output_schema_id="r",
)
DEFAULTED_TEMPLATE = BindingTemplate(
    binding_id="notes-mem.archive", contract_id=DEFAULTED_CREATE.contract_id
)


def _task(task_id: str = NOTES_TASK.task_id, **changes: Any) -> TaskDefinition:
    """NOTES_TASK with changes, validated; a Budgets instance keeps its set fields."""
    base = NOTES_TASK.model_dump(exclude={"budgets"})
    return TaskDefinition.model_validate({**base, "task_id": task_id, **changes})


def _register_tasks(
    reg: PluginRegistry,
    *tasks: TaskDefinition,
    plugin_id: str = "notes-fixture",
    capabilities: tuple[CapabilityDescriptor, ...] = (READ, CREATE),
    templates: tuple[BindingTemplate, ...] = BINDINGS,
) -> None:
    reg.register(
        plugin_id=plugin_id,
        plugin_version="1",
        declared_capabilities=capabilities,
        binding_templates=templates,
        declared_task_definitions=tuple(
            TaskDeclaration(task_id=t.task_id, version=t.version) for t in tasks
        ),
        contribution=PluginContribution(capabilities=capabilities, task_definitions=tasks),
    )


def _refused(action: Any) -> str:
    with pytest.raises(KernelError) as exc:
        action()
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    return exc.value.safe_message


def test_notes_domain_task_definition_admitted() -> None:
    reg = PluginRegistry(BOTH_BOUND)
    _register_tasks(reg, NOTES_TASK)
    assert reg.task_definitions == {}  # staged until every plugin is registered
    reg.admit_task_definitions()
    assert reg.task_definitions == {NOTES_TASK.task_id: NOTES_TASK}
    assert reg.report.admitted == ["notes-fixture"]


def test_registry_refuses_task_with_unadmitted_capability() -> None:
    # A contract no pack declares.
    unknown = _task(capabilities=(READ.contract_id, CREATE.contract_id, "notes.note.purge.v1"))
    reg = PluginRegistry(BOTH_BOUND)
    _register_tasks(reg, unknown)
    message = _refused(reg.admit_task_definitions)
    assert "notes.note.purge.v1" in message
    assert reg.task_definitions == {}
    # A declared capability whose binding has no connection in this profile.
    reg = PluginRegistry({"notes-mem.read": ("c1",)})
    _register_tasks(reg, NOTES_TASK)
    message = _refused(reg.admit_task_definitions)
    assert CREATE.contract_id in message
    assert "no admitted binding" in message


def test_registry_refuses_task_naming_a_host_only_capability() -> None:
    hidden = READ.model_copy(update={"contract_id": "notes.note.audit.v1", "agent_visible": False})
    reg = PluginRegistry({**BOTH_BOUND, "notes-mem.audit": ("c1",)})
    _register_tasks(
        reg,
        _task(capabilities=(READ.contract_id, CREATE.contract_id, hidden.contract_id)),
        capabilities=(READ, CREATE, hidden),
        templates=(
            *BINDINGS,
            BindingTemplate(binding_id="notes-mem.audit", contract_id=hidden.contract_id),
        ),
    )
    assert hidden.contract_id in _refused(reg.admit_task_definitions)


def test_registry_refuses_duplicate_task_id() -> None:
    reg = PluginRegistry(BOTH_BOUND)
    _register_tasks(reg, NOTES_TASK)
    # Another pack, even with an equal definition, may not reuse the task id.
    message = _refused(
        lambda: _register_tasks(reg, NOTES_TASK, plugin_id="other", capabilities=(), templates=())
    )
    assert NOTES_TASK.task_id in message
    # Nor may one pack contribute it twice.
    reg = PluginRegistry(BOTH_BOUND)
    assert NOTES_TASK.task_id in _refused(
        lambda: _register_tasks(reg, NOTES_TASK, _task(version="2"))
    )


def test_task_definitions_must_match_manifest() -> None:
    reg = PluginRegistry(BOTH_BOUND)
    message = _refused(
        lambda: reg.register(
            plugin_id="notes-fixture",
            plugin_version="1",
            declared_capabilities=(READ, CREATE),
            binding_templates=BINDINGS,
            declared_task_definitions=(TaskDeclaration(task_id=NOTES_TASK.task_id, version="9"),),
            contribution=PluginContribution(
                capabilities=(READ, CREATE), task_definitions=(NOTES_TASK,)
            ),
        )
    )
    assert "task definitions differ from manifest" in message


def test_definition_budgets_only_narrow() -> None:
    profile = Budgets(max_read_calls=10, max_admitted_writes=2)
    # Only fields the definition sets count: max_driver_turns keeps the profile's value.
    narrow = _task(budgets=Budgets(max_read_calls=5, max_admitted_writes=2))
    reg = PluginRegistry(BOTH_BOUND, budgets=profile)
    _register_tasks(reg, narrow)
    reg.admit_task_definitions()
    assert reg.task_definitions[narrow.task_id].budgets == narrow.budgets
    for wider in (Budgets(max_read_calls=11), Budgets(max_driver_turns=13)):
        reg = PluginRegistry(BOTH_BOUND, budgets=profile)
        message = _refused(lambda w=wider: _register_tasks(reg, _task(budgets=w)))
        assert NOTES_TASK.task_id in message
        assert next(iter(wider.model_fields_set)) in message
        assert reg.report.admitted == []
    # A field left at its default never counts, even when the default is wider.
    reg = PluginRegistry(BOTH_BOUND, budgets=Budgets(max_driver_turns=3))
    _register_tasks(reg, _task(budgets=Budgets(max_read_calls=1)))
    reg.admit_task_definitions()


def test_live_profile_refuses_defaulted_write_declaration() -> None:
    # A write capability relying on defaulted risk and reversibility.
    reg = PluginRegistry({}, environment="live")
    message = _refused(lambda: _register_tasks(reg, capabilities=(DEFAULTED_CREATE,), templates=()))
    assert DEFAULTED_CREATE.contract_id in message
    assert "risk" in message and "reversibility" in message
    # A connected write binding relying on the defaulted idempotency.
    declared_create = CapabilityDescriptor(
        **DEFAULTED_CREATE.model_dump(exclude={"risk", "reversibility"}),
        risk=CREATE.risk,
        reversibility=CREATE.reversibility,
    )
    reg = PluginRegistry({DEFAULTED_TEMPLATE.binding_id: ("c1",)}, environment="live")
    message = _refused(
        lambda: _register_tasks(
            reg, capabilities=(declared_create,), templates=(DEFAULTED_TEMPLATE,)
        )
    )
    assert DEFAULTED_TEMPLATE.binding_id in message
    assert "idempotency" in message
    # Explicit declarations, as the notes fixture makes, are admitted live.
    reg = PluginRegistry(BOTH_BOUND, environment="live")
    _register_tasks(reg, NOTES_TASK)
    reg.admit_task_definitions()
    assert reg.report.defaulted_declarations == []


def test_fixture_profile_reports_defaulted_declarations() -> None:
    reg = PluginRegistry({DEFAULTED_TEMPLATE.binding_id: ("c1",)})
    _register_tasks(reg, capabilities=(DEFAULTED_CREATE,), templates=(DEFAULTED_TEMPLATE,))
    assert reg.report.admitted == ["notes-fixture"]
    assert reg.report.defaulted_declarations == [
        DefaultedDeclaration(
            plugin_id="notes-fixture",
            subject="capability",
            subject_id=DEFAULTED_CREATE.contract_id,
            fields=("reversibility", "risk"),
        ),
        DefaultedDeclaration(
            plugin_id="notes-fixture",
            subject="binding",
            subject_id=DEFAULTED_TEMPLATE.binding_id,
            fields=("idempotency",),
        ),
    ]
    # Reads and unconnected templates are not reported.
    reg = PluginRegistry({})
    _register_tasks(reg, capabilities=(READ,), templates=(BINDINGS[0],))
    assert reg.report.defaulted_declarations == []


def test_registry_copies_binding_idempotency() -> None:
    reg = PluginRegistry({**BOTH_BOUND, DEFAULTED_TEMPLATE.binding_id: ("c1",)})
    _register_tasks(
        reg,
        capabilities=(READ, CREATE, DEFAULTED_CREATE),
        templates=(*BINDINGS, DEFAULTED_TEMPLATE),
    )
    declared = reg.resolve(CREATE.contract_id, "c1")
    assert declared.idempotency is Idempotency.PROVIDER_KEY
    assert "idempotency" in declared.model_fields_set
    defaulted = reg.resolve(DEFAULTED_CREATE.contract_id, "c1")
    assert defaulted.idempotency is Idempotency.NONE
    assert "idempotency" not in defaulted.model_fields_set  # still detectable


def test_pack_without_task_definitions_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The discovered pack's manifest declares no task definitions, like the
    # check_core_only.py test pack.
    _install(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    reg = PluginRegistry({})
    try:
        report = reg.admit(
            discover([str(tmp_path)]),
            {"notes-fixture": EnabledPlugin("0.3.0", allow_unverified_fixture=True)},
        )
    finally:  # the package is this test's alone
        for name in ("notes_fixture.plugin", "notes_fixture"):
            sys.modules.pop(name, None)
    assert report.admitted == ["notes-fixture"]
    reg.admit_task_definitions()
    assert reg.task_definitions == {}
