"""Plugins depend only on the common base (ADR 0026, its common-SDK amendment).

Each plugin distribution (one with an ``e_agent.plugins.v1`` entry point in
``dists/*/pyproject.toml``) may depend on ``e-agent-contracts``, ``e-agent-plugin-sdk``
and, for a provider, the domain packs whose capabilities it binds. The plugin kind
and the contracts come from the plugin manifests, not from a hand-kept list.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest
from e_agent.sdk import ENTRY_POINT_GROUP, MANIFEST_FILENAME
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REPO = Path(__file__).resolve().parents[2]
COMMON_BASE = frozenset({"e-agent-contracts", "e-agent-plugin-sdk"})
CORE_CONTRACT = "Core packages do not import agent frameworks or provider SDKs"


@dataclass(frozen=True)
class PluginDist:
    name: str
    kind: str
    requires: frozenset[str]
    provides: frozenset[str]
    binds: frozenset[str]


def _plugin_dists() -> list[PluginDist]:
    found = []
    for config in sorted(REPO.glob("dists/*/pyproject.toml")):
        project = tomllib.loads(config.read_text("utf-8"))["project"]
        for value in project.get("entry-points", {}).get(ENTRY_POINT_GROUP, {}).values():
            package = value.split(":", 1)[0].rpartition(".")[0]
            manifest_path = REPO / "src" / Path(*package.split(".")) / MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_text("utf-8"))
            found.append(
                PluginDist(
                    name=canonicalize_name(project["name"]),
                    kind=manifest["kind"],
                    requires=frozenset(
                        canonicalize_name(Requirement(r).name)
                        for r in project.get("dependencies", [])
                    ),
                    provides=frozenset(c["contract_id"] for c in manifest["provides_capabilities"]),
                    binds=frozenset(b["contract_id"] for b in manifest["provides_bindings"]),
                )
            )
    return found


def _outside_base(plugins: Iterable[PluginDist]) -> list[str]:
    """Each plugin's e-agent dependencies beyond its allowance; no plugin at all is an error."""
    plugins = list(plugins)
    if not plugins:
        raise AssertionError(f"no {ENTRY_POINT_GROUP} plugin distributions found")
    owner = {c: p.name for p in plugins if p.kind == "domain" for c in p.provides}
    problems = []
    for plugin in plugins:
        allowed = set(COMMON_BASE)
        if plugin.kind == "provider":
            allowed |= {owner[c] for c in plugin.binds if c in owner}
        extra = {r for r in plugin.requires if r.startswith("e-agent-")} - allowed
        problems += [f"{plugin.name} -> {name}" for name in sorted(extra)]
    return problems


def test_plugin_dependencies_are_the_common_base() -> None:
    plugins = _plugin_dists()
    print(f"checked {len(plugins)} plugin distributions")
    assert _outside_base(plugins) == []


def test_dependency_check_fails_on_zero_plugins() -> None:
    with pytest.raises(AssertionError, match=re.escape(f"no {ENTRY_POINT_GROUP} plugin")):
        _outside_base([])


def test_dependency_check_reports_core_and_unbound_domain_dependencies() -> None:
    domain = PluginDist(
        "e-agent-domain-a", "domain", COMMON_BASE, frozenset({"a.read.v1"}), frozenset()
    )
    other = PluginDist(
        "e-agent-domain-b", "domain", COMMON_BASE, frozenset({"b.read.v1"}), frozenset()
    )
    provider = PluginDist(
        "e-agent-adapter-x",
        "provider",
        COMMON_BASE | {"e-agent-domain-a", "e-agent-domain-b", "e-agent-kernel", "httpx"},
        frozenset(),
        frozenset({"a.read.v1"}),
    )
    assert _outside_base([domain, other, provider]) == [
        "e-agent-adapter-x -> e-agent-domain-b",
        "e-agent-adapter-x -> e-agent-kernel",
    ]


def test_core_contract_exempts_only_the_sdk_http_module() -> None:
    config = tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))
    [contract] = [
        c for c in config["tool"]["importlinter"]["contracts"] if c["name"] == CORE_CONTRACT
    ]
    assert "httpx" in contract["forbidden_modules"]
    assert contract.get("ignore_imports") == ["e_agent.sdk.http -> httpx"]
    for other in config["tool"]["importlinter"]["contracts"]:
        if other["name"] != CORE_CONTRACT:
            assert "ignore_imports" not in other, other["name"]
