"""Plugin registry: admission, activation and binding resolution (MVP design §6).

Admission happens before any plugin code is imported. Disabled or unknown
plugins are never imported. Conflicts fail closed at startup.
"""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from e_agent.contracts.capability import CapabilityBinding, CapabilityDescriptor
from e_agent.sdk import SDK_API_VERSION
from e_agent.sdk.discovery import DiscoveredPlugin
from e_agent.sdk.manifest import BindingTemplate
from e_agent.sdk.ports import (
    ActionExecutor,
    AgentDriver,
    OutcomeVerifier,
    PlanValidator,
    PluginContribution,
    PluginServices,
)
from e_agent.sdk.validation import ValidationDatasetBuilder

from .errors import ErrorCode, KernelError


@dataclass(frozen=True)
class EnabledPlugin:
    version: str
    manifest_sha256: str | None = None
    settings: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class AdmissionReport:
    admitted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _reject(message: str) -> KernelError:
    return KernelError(ErrorCode.STARTUP_REJECTED, message)


class PluginRegistry:
    def __init__(self, binding_connections: Mapping[str, Iterable[str]]) -> None:
        self._binding_connections = {k: tuple(v) for k, v in binding_connections.items()}
        self.capabilities: dict[str, CapabilityDescriptor] = {}
        self.bindings: list[CapabilityBinding] = []
        self._binding_owner: dict[str, str] = {}
        self.validators: list[PlanValidator] = []
        self.executors: list[ActionExecutor] = []
        self.verifiers: list[OutcomeVerifier] = []
        self.drivers: list[AgentDriver] = []
        self.dataset_builders: list[ValidationDatasetBuilder] = []
        self.input_schemas: dict[str, Mapping[str, Any]] = {}
        self.agent_guidance: list[str] = []
        self.report = AdmissionReport()

    def surface_digest(self) -> str:
        """Digest of the tool surface a run is planned against (threat model T17):
        capabilities, their input schemas, bindings and plugin versions."""
        import hashlib
        import json

        surface = {
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
            creds = credentials_for(pid) if credentials_for is not None else None
            contribution = self._load(plugin, config, creds)
            self.register(
                plugin_id=pid,
                plugin_version=plugin.manifest.version,
                declared_capabilities=plugin.manifest.provides_capabilities,
                binding_templates=plugin.manifest.provides_bindings,
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
        if not manifest.supports_sdk(SDK_API_VERSION):
            raise _reject(f"{pid}: incompatible SDK API range {manifest.sdk_api}")
        if plugin.entry_point_value != manifest.factory:
            raise _reject(f"{pid}: entry point does not match manifest factory")

    @staticmethod
    def _load(
        plugin: DiscoveredPlugin, config: EnabledPlugin, credentials: Any = None
    ) -> PluginContribution:
        module_name, _, attr = plugin.manifest.factory.partition(":")
        factory = getattr(importlib.import_module(module_name), attr)
        contribution = factory(
            PluginServices(settings=dict(config.settings), credentials=credentials)
        )
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
    ) -> None:
        declared = set(declared_capabilities)
        if set(contribution.capabilities) != declared:
            raise _reject(f"{plugin_id}: registered capabilities differ from manifest")
        for cap in declared:
            existing = self.capabilities.get(cap.contract_id)
            if existing is not None and existing != cap:
                raise _reject(f"conflicting definitions for {cap.contract_id}")
            self.capabilities[cap.contract_id] = cap
        for template in binding_templates:
            if template.binding_id in self._binding_owner:
                raise _reject(f"duplicate binding id {template.binding_id!r}")
            if template.contract_id not in self.capabilities:
                raise _reject(f"binding {template.binding_id} for unknown contract")
            self._binding_owner[template.binding_id] = plugin_id
            for connection_id in self._binding_connections.get(template.binding_id, ()):
                self.bindings.append(
                    CapabilityBinding(
                        binding_id=template.binding_id,
                        contract_id=template.contract_id,
                        plugin_id=plugin_id,
                        plugin_version=plugin_version,
                        connection_id=connection_id,
                        supported_features=template.supported_features,
                    )
                )
        self.validators.extend(contribution.validators)
        self.executors.extend(contribution.executors)
        self.verifiers.extend(contribution.verifiers)
        self.drivers.extend(contribution.drivers)
        self.dataset_builders.extend(contribution.dataset_builders)
        for schema_id, schema in contribution.input_schemas.items():
            if schema_id in self.input_schemas and self.input_schemas[schema_id] != schema:
                raise _reject(f"conflicting schema definitions for {schema_id}")
            self.input_schemas[schema_id] = schema
        if contribution.agent_guidance:
            self.agent_guidance.append(contribution.agent_guidance)
        self.report.admitted.append(plugin_id)

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
