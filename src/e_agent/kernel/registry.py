"""Plugin registry: admission, activation and binding resolution (MVP design §6).

Admission happens before any plugin code is imported. Disabled or unknown
plugins are never imported. Conflicts fail closed at startup.
"""

from __future__ import annotations

import hashlib
import importlib
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Literal

from e_agent.contracts import data_classes as dc
from e_agent.contracts.capability import CapabilityBinding, CapabilityDescriptor, EffectKind
from e_agent.contracts.context import Budgets
from e_agent.contracts.task import TaskDefinition, check_answer_condition
from e_agent.sdk import SDK_API_VERSION
from e_agent.sdk.connection import ConnectionSpec
from e_agent.sdk.discovery import DiscoveredPlugin, DiscoveryError, artifact_digest
from e_agent.sdk.errors import InvalidPluginSettings
from e_agent.sdk.manifest import BindingTemplate, TaskDeclaration
from e_agent.sdk.ports import (
    ActionExecutor,
    AgentDriver,
    DriverFactory,
    OutcomeVerifier,
    PlanValidator,
    PluginContribution,
    PluginServices,
    TaskPreset,
)
from e_agent.sdk.validation import ValidationDatasetBuilder
from pydantic import ValidationError

from .errors import ErrorCode, KernelError
from .registry_records import AdmissionReport, DefaultedDeclaration, EnabledPlugin

__all__ = ["AdmissionReport", "DefaultedDeclaration", "EnabledPlugin", "PluginRegistry"]


def _reject(message: str) -> KernelError:
    return KernelError(ErrorCode.STARTUP_REJECTED, message)


_CAPABILITY_EFFECT_FIELDS = frozenset({"risk", "reversibility"})
_BINDING_EFFECT_FIELDS = frozenset({"idempotency"})

_SETTING_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}")


def _settings_rejection(plugin_id: str, exc: InvalidPluginSettings) -> KernelError:
    """The operator's message names the setting and the plugin's reason, never a value.

    A setting name comes from the profile too, so only a plain name is shown.
    """
    name = exc.setting if _SETTING_NAME.fullmatch(exc.setting) else "<unnamed setting>"
    return _reject(f"{plugin_id}: invalid setting {name!r}: {exc.reason}")


class PluginRegistry:
    def __init__(
        self,
        binding_connections: Mapping[str, Iterable[str]],
        *,
        environment: Literal["fixture", "live"] = "fixture",
        budgets: Budgets | None = None,
    ) -> None:
        """``environment`` and ``budgets`` are the profile's: a live registry refuses a
        defaulted write effect declaration (ADR 0029), and a task definition's budgets
        may only narrow ``budgets`` (ADR 0028, D7). Bootstrap passes both."""
        self._binding_connections = {k: tuple(v) for k, v in binding_connections.items()}
        self.environment = environment
        self._classes: dict[str, Mapping[str, dc.DataClass]] = {}  # frozen at admission
        self.budgets = budgets if budgets is not None else Budgets()
        self.capabilities: dict[str, CapabilityDescriptor] = {}
        self.bindings: list[CapabilityBinding] = []
        self._binding_owner: dict[str, str] = {}
        self.validators: list[PlanValidator] = []
        self.executors: list[ActionExecutor] = []
        self.verifiers: list[OutcomeVerifier] = []
        self.drivers: list[AgentDriver] = []
        self.dataset_builders: list[ValidationDatasetBuilder] = []
        self.input_schemas: dict[str, Mapping[str, Any]] = {}
        self.output_schemas: dict[str, Mapping[str, Any]] = {}
        """For class pointers only (ADR 0030): never model-facing, not in the surface digest."""
        self.agent_guidance: list[str] = []
        self.task_presets: dict[str, TaskPreset] = {}
        self.task_definitions: dict[str, TaskDefinition] = {}
        """Admitted task definitions by ``task_id`` (ADR 0028), filled by
        ``admit_task_definitions`` once every plugin is registered."""
        self._staged_tasks: list[TaskDefinition] = []
        self._task_owner: dict[str, str] = {}
        self.driver_factories: dict[str, DriverFactory] = {}
        self.report = AdmissionReport()
        self._admitted_inventory: dict[str, dict[str, Any]] = {}
        self.connection_specs: dict[str, ConnectionSpec] = {}
        """Admitted plugins' manifest ``connection`` sections (ADR 0012 item 1)."""
        self.auth_placements: dict[str, dict[str, str]] = {}
        """Credential placement per admitted plugin, filled before its code loads."""
        self.plugin_executors: dict[str, tuple[ActionExecutor, ...]] = {}
        self.diagnostics: dict[str, Callable[[], Mapping[str, Any]]] = {}
        """Admitted plugins' diagnostics hooks, by plugin id (fixture runs and tests)."""

    def surface_digest(self) -> str:
        """Digest of the tool surface a run is planned against (threat model T17):
        capabilities, their input schemas, bindings and plugin versions."""
        import hashlib
        import json

        surface = {
            "admission": self._admitted_inventory,
            "capabilities": {
                cid: [c.effect.value, c.input_schema_id, self.input_schemas.get(c.input_schema_id)]
                for cid, c in sorted(self.capabilities.items())
            },
            "bindings": sorted(
                (b.binding_id, b.contract_id, b.connection_id, b.plugin_id, b.plugin_version)
                for b in self.bindings
            ),
        }
        canonical = json.dumps(surface, sort_keys=True, separators=(",", ":"), default=str)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # -- admission ------------------------------------------------------------
    def admit(
        self,
        discovered: Iterable[DiscoveredPlugin],
        enabled: Mapping[str, EnabledPlugin],
        credentials_for: Callable[[str], Any] | None = None,
    ) -> AdmissionReport:
        found: dict[str, DiscoveredPlugin] = {}
        for plugin in discovered:
            pid = plugin.manifest.plugin_id
            if pid in found:
                raise _reject(f"plugin id {pid!r} provided by two distributions")
            found[pid] = plugin
        missing = sorted(set(enabled) - set(found))
        if missing:
            raise _reject(f"enabled plugins not installed: {missing}")
        for pid, plugin in sorted(found.items()):
            config = enabled.get(pid)
            if config is None:
                self.report.skipped.append(pid)  # never imported
                continue
            self._check_admissible(plugin, config)
            self._admit_connection(plugin)
            self._admitted_inventory[pid] = {
                "version": config.version,
                "artifact_sha256": config.artifact_sha256,
                "settings": dict(config.settings),
            }
            creds = credentials_for(pid) if credentials_for is not None else None
            contribution = self._load(plugin, config, creds)
            self.register(
                plugin_id=pid,
                plugin_version=plugin.manifest.version,
                declared_capabilities=plugin.manifest.provides_capabilities,
                binding_templates=plugin.manifest.provides_bindings,
                declared_task_definitions=plugin.manifest.provides_task_definitions,
                contribution=contribution,
            )
        return self.report

    @staticmethod
    def _check_admissible(plugin: DiscoveredPlugin, config: EnabledPlugin) -> None:
        manifest = plugin.manifest
        pid = manifest.plugin_id
        if manifest.version != config.version or plugin.distribution_version != config.version:
            raise _reject(f"{pid}: installed version does not match the approved inventory")
        if config.manifest_sha256 is not None:
            actual = hashlib.sha256(plugin.manifest_text.encode("utf-8")).hexdigest()
            if actual != config.manifest_sha256:
                raise _reject(f"{pid}: manifest digest does not match the approved inventory")
        if config.artifact_sha256 is not None:
            try:
                actual = artifact_digest(plugin.artifact_files)
            except (DiscoveryError, OSError) as exc:
                raise _reject(f"{pid}: artifact inventory unavailable") from exc
            if actual != config.artifact_sha256:
                raise _reject(f"{pid}: artifact bytes differ from the approved build inventory")
        elif not config.allow_unverified_fixture:
            raise _reject(f"{pid}: an approved artifact inventory is required")
        if not manifest.supports_sdk(SDK_API_VERSION):
            raise _reject(f"{pid}: incompatible SDK API range {manifest.sdk_api}")
        if plugin.entry_point_value != manifest.factory:
            raise _reject(f"{pid}: entry point does not match manifest factory")

    def _admit_connection(self, plugin: DiscoveredPlugin) -> None:
        pid = plugin.manifest.plugin_id
        try:
            spec = ConnectionSpec.from_manifest(plugin.manifest.connection)
        except ValidationError as exc:
            reasons = "; ".join(str(e["msg"]) for e in exc.errors())
            raise _reject(f"{pid}: invalid manifest connection section: {reasons}") from exc
        if spec is None:
            return
        self.connection_specs[pid] = spec
        placement = spec.placement()
        if placement is not None:
            self.auth_placements[pid] = placement

    @staticmethod
    def _load(
        plugin: DiscoveredPlugin, config: EnabledPlugin, credentials: Any = None
    ) -> PluginContribution:
        module_name, _, attr = plugin.manifest.factory.partition(":")
        factory = getattr(importlib.import_module(module_name), attr)
        try:
            contribution = factory(
                PluginServices(settings=dict(config.settings), credentials=credentials)
            )
        except InvalidPluginSettings as exc:
            raise _settings_rejection(plugin.manifest.plugin_id, exc) from exc
        if not isinstance(contribution, PluginContribution):
            raise _reject(f"{plugin.manifest.plugin_id}: factory returned an invalid contribution")
        return contribution

    # -- registration -----------------------------------------------------------
    def register(
        self,
        *,
        plugin_id: str,
        plugin_version: str,
        declared_capabilities: Iterable[CapabilityDescriptor],
        binding_templates: Iterable[BindingTemplate],
        contribution: PluginContribution,
        declared_task_definitions: Iterable[TaskDeclaration] = (),
    ) -> None:
        declared = set(declared_capabilities)
        if set(contribution.capabilities) != declared:
            raise _reject(f"{plugin_id}: registered capabilities differ from manifest")
        self._stage_task_definitions(plugin_id, tuple(declared_task_definitions), contribution)
        for cap in sorted(declared, key=lambda c: c.contract_id):
            existing = self.capabilities.get(cap.contract_id)
            if existing is not None and existing != cap:
                raise _reject(f"conflicting definitions for {cap.contract_id}")
            if cap.effect is EffectKind.WRITE:
                self._check_defaults(
                    plugin_id, "capability", cap.contract_id, cap, _CAPABILITY_EFFECT_FIELDS
                )
            self.capabilities[cap.contract_id] = cap
            self._classes[cap.contract_id] = dc.frozen_classes(cap.data_classes)
        for template in binding_templates:
            if template.binding_id in self._binding_owner:
                raise _reject(f"duplicate binding id {template.binding_id!r}")
            if template.contract_id not in self.capabilities:
                raise _reject(f"binding {template.binding_id} for unknown contract")
            required = self.capabilities[template.contract_id].required_features
            missing = sorted(required - template.supported_features)
            if missing:
                raise _reject(
                    f"{plugin_id}: binding {template.binding_id} for {template.contract_id} "
                    f"lacks required features {missing}"
                )
            self._binding_owner[template.binding_id] = plugin_id
            connections = self._binding_connections.get(template.binding_id, ())
            # Only a connected template becomes a binding a run can route to.
            if connections and self.capabilities[template.contract_id].effect is EffectKind.WRITE:
                self._check_defaults(
                    plugin_id, "binding", template.binding_id, template, _BINDING_EFFECT_FIELDS
                )
            # Copied only when declared, so a defaulted idempotency stays detectable.
            declared_effects = (
                {"idempotency": template.idempotency}
                if "idempotency" in template.model_fields_set
                else {}
            )
            for connection_id in connections:
                self.bindings.append(
                    CapabilityBinding(
                        binding_id=template.binding_id,
                        contract_id=template.contract_id,
                        plugin_id=plugin_id,
                        plugin_version=plugin_version,
                        connection_id=connection_id,
                        supported_features=template.supported_features,
                        **declared_effects,
                    )
                )
        self.validators.extend(contribution.validators)
        self.executors.extend(contribution.executors)
        self.plugin_executors[plugin_id] = tuple(contribution.executors)
        if contribution.diagnostics is not None:
            self.diagnostics[plugin_id] = contribution.diagnostics
        self.verifiers.extend(contribution.verifiers)
        self.drivers.extend(contribution.drivers)
        self.dataset_builders.extend(contribution.dataset_builders)
        for schema_id, schema in contribution.input_schemas.items():
            if schema_id in self.input_schemas and self.input_schemas[schema_id] != schema:
                raise _reject(f"conflicting schema definitions for {schema_id}")
            self.input_schemas[schema_id] = schema
        for schema_id, schema in contribution.output_schemas.items():
            if schema_id in self.output_schemas and self.output_schemas[schema_id] != schema:
                raise _reject(f"conflicting schema definitions for {schema_id}")
            self.output_schemas[schema_id] = schema
        for cap in sorted(declared, key=lambda c: c.contract_id):  # ADR 0030 class paths
            try:
                dc.check_declarations(self.schema_document(cap.contract_id), cap.data_classes)
            except ValueError as exc:
                raise _reject(f"{plugin_id}: {cap.contract_id} {exc}") from None
        if contribution.agent_guidance:
            self.agent_guidance.append(contribution.agent_guidance)
        for preset in contribution.task_presets:
            if preset.kind in self.task_presets and self.task_presets[preset.kind] != preset:
                raise _reject(f"conflicting task presets for {preset.kind}")
            self.task_presets[preset.kind] = preset
        for kind, factory in contribution.driver_factories.items():
            if kind in self.driver_factories:
                raise _reject(f"driver kind {kind!r} contributed by two plugins")
            self.driver_factories[kind] = factory
        self._staged_tasks.extend(contribution.task_definitions)
        for task in contribution.task_definitions:
            self._task_owner[task.task_id] = plugin_id
        self.report.admitted.append(plugin_id)

    def _check_defaults(
        self,
        plugin_id: str,
        subject: Literal["capability", "binding"],
        subject_id: str,
        record: CapabilityDescriptor | BindingTemplate,
        effect_fields: frozenset[str],
    ) -> None:
        """ADR 0029: a live profile refuses a write that relies on a default effect field;
        a fixture profile admits it and reports it."""
        defaulted = tuple(sorted(effect_fields - record.model_fields_set))
        if not defaulted:
            return
        if self.environment == "live":
            raise _reject(
                f"{plugin_id}: write {subject} {subject_id} relies on defaulted effect "
                f"declarations {list(defaulted)}; a live profile requires them declared"
            )
        self.report.defaulted_declarations.append(
            DefaultedDeclaration(plugin_id, subject, subject_id, defaulted)
        )

    # -- data classes (ADR 0030) -------------------------------------------------
    def schema_document(self, contract_id: str) -> dict[str, Mapping[str, Any]]:
        """The registered schemas of a capability, as ``{"input": ..., "output": ...}``."""
        cap = self.descriptor(contract_id)
        return dc.schema_document(
            self.input_schemas.get(cap.input_schema_id),
            self.output_schemas.get(cap.output_schema_id),
        )

    def data_class(self, contract_id: str, instance_path: str) -> dc.DataClass:
        """The most restrictive class declared on the path or an ancestor, ``personal``
        when none; string work, no schema walk."""
        return dc.class_for(self.data_classes(contract_id), instance_path)

    def data_classes(self, contract_id: str) -> Mapping[str, dc.DataClass]:
        """The capability's declarations as admitted (a frozen copy, review C3-14): the
        lookup the context assembler classes observation values with (Task 3d.2)."""
        return self._classes[self.descriptor(contract_id).contract_id]

    def unmarked_properties(self) -> dict[str, dict[str, int | None]]:
        """Unmarked leaves per capability and side; None: no schema, or an unsupported one."""
        caps = sorted(self.capabilities.items())
        return {
            cid: dc.unmarked_counts(self.schema_document(cid), c.data_classes) for cid, c in caps
        }

    def unsupported_schemas(self) -> dict[str, dict[str, str]]:
        """Sides whose schema leaves the data-class subset (every value there is personal)."""
        found = {cid: dc.unsupported_sides(self.schema_document(cid)) for cid in self.capabilities}
        return {cid: sides for cid, sides in sorted(found.items()) if sides}

    # -- task definitions (ADR 0028) ----------------------------------------------
    def _stage_task_definitions(
        self,
        plugin_id: str,
        declared: tuple[TaskDeclaration, ...],
        contribution: PluginContribution,
    ) -> None:
        """Checks that need no other plugin: the manifest, duplicate ids, budgets and the
        acceptance answer condition."""
        tasks = contribution.task_definitions
        contributed = sorted((t.task_id, t.version) for t in tasks)
        if contributed != sorted((d.task_id, d.version) for d in declared):
            raise _reject(f"{plugin_id}: registered task definitions differ from manifest")
        seen: set[str] = set()
        for task in tasks:
            if task.task_id in seen or task.task_id in self._task_owner:
                raise _reject(f"{plugin_id}: duplicate task id {task.task_id!r}")
            seen.add(task.task_id)
            self._check_task_budgets(plugin_id, task)
            try:
                # The record checks it; a built record skips validation (Codex review C-2).
                check_answer_condition(task.acceptance)
            except ValueError as exc:
                raise _reject(f"{plugin_id}: task {task.task_id!r}: {exc}") from None

    def _check_task_budgets(self, plugin_id: str, task: TaskDefinition) -> None:
        """A definition's budgets only narrow the profile's (D7). ``Budgets`` has
        defaults, so only the fields the definition sets are compared."""
        if task.budgets is None:
            return
        wider = sorted(
            name
            for name in task.budgets.model_fields_set
            if getattr(task.budgets, name) > getattr(self.budgets, name)
        )
        if wider:
            raise _reject(
                f"{plugin_id}: task {task.task_id!r} budgets {wider} are wider than the profile's"
            )

    def admit_task_definitions(self) -> None:
        """Admit staged task definitions once every plugin is registered (ADR 0028).

        Each capability must be an admitted, agent-visible capability; a read or write
        also needs an admitted binding (a template mapped to a connection). An answer
        has no provider binding: it verifies through the run's read connection, as in
        the run's tool set. The composition root calls this once every plugin is
        admitted and its connection checks pass; until then a staged definition is
        not in ``task_definitions``, so no run can resolve it.
        """
        bound = {b.contract_id for b in self.bindings}
        for task in self._staged_tasks:
            owner = self._task_owner[task.task_id]
            for contract_id in task.capabilities:
                cap = self.capabilities.get(contract_id)
                if cap is None:
                    raise _reject(
                        f"{owner}: task {task.task_id!r} names capability {contract_id}, "
                        "which no admitted plugin declares"
                    )
                if not cap.agent_visible:
                    raise _reject(
                        f"{owner}: task {task.task_id!r} names host-only capability {contract_id}"
                    )
                if cap.effect is not EffectKind.ANSWER and contract_id not in bound:
                    raise _reject(
                        f"{owner}: task {task.task_id!r} capability {contract_id} "
                        "has no admitted binding"
                    )
        for task in self._staged_tasks:
            self.task_definitions[task.task_id] = task
        self._staged_tasks.clear()

    # -- resolution -------------------------------------------------------------
    def descriptor(self, contract_id: str) -> CapabilityDescriptor:
        try:
            return self.capabilities[contract_id]
        except KeyError:
            raise KernelError(ErrorCode.INVALID_REQUEST, "unknown capability") from None

    def resolve(self, contract_id: str, connection_id: str) -> CapabilityBinding:
        candidates = [
            b
            for b in self.bindings
            if b.contract_id == contract_id and b.connection_id == connection_id
        ]
        if not candidates:
            raise KernelError(ErrorCode.FORBIDDEN, "no binding for capability on connection")
        if len(candidates) > 1:
            raise KernelError(ErrorCode.CONFLICT, "ambiguous binding; refusing to choose")
        return candidates[0]

    def executor_for(self, binding: CapabilityBinding) -> ActionExecutor:
        matches = [e for e in self.executors if e.supports(binding)]
        if len(matches) != 1:
            raise KernelError(ErrorCode.DEPENDENCY_UNAVAILABLE, "no unique executor for binding")
        return matches[0]

    def validators_for(self, contract_id: str) -> list[PlanValidator]:
        return [v for v in self.validators if v.supports(contract_id)]

    def verifier_for(self, contract_id: str) -> OutcomeVerifier | None:
        matches = [v for v in self.verifiers if v.supports(contract_id)]
        if len(matches) > 1:
            raise KernelError(ErrorCode.CONFLICT, "ambiguous verifier")
        return matches[0] if matches else None
