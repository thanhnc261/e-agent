"""Every installed plugin package is a source of "Plugins are guests" (XA-02, PR-08).

The plugin packages come from the installed ``e_agent.plugins.v1`` entry points,
not from a hand-kept list, so a new provider cannot escape the contract.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from e_agent.sdk import ENTRY_POINT_GROUP

REPO = Path(__file__).resolve().parents[2]
GUEST_CONTRACT = "Plugins are guests"


def _guest_sources() -> list[str]:
    config = tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))
    contracts = config["tool"]["importlinter"]["contracts"]
    [contract] = [c for c in contracts if c["name"] == GUEST_CONTRACT]
    return list(contract["source_modules"])


def _plugin_package(entry_value: str) -> str:
    """``e_agent.adapters.odoo.plugin:create_plugin`` -> ``e_agent.adapters.odoo``."""
    return entry_value.split(":", 1)[0].rpartition(".")[0]


def _unguarded(entry_values: Iterable[str], sources: Iterable[str]) -> list[str]:
    """The plugin packages outside the contract's sources; no plugin at all is an error."""
    packages = sorted({_plugin_package(value) for value in entry_values})
    if not packages:
        raise AssertionError(f"no {ENTRY_POINT_GROUP} entry points found")
    guarded = tuple(sources)
    return [
        pkg for pkg in packages if not any(pkg == s or pkg.startswith(f"{s}.") for s in guarded)
    ]


def test_every_plugin_package_is_a_guest() -> None:
    values = [ep.value for ep in entry_points(group=ENTRY_POINT_GROUP)]
    print(f"checked {len(values)} plugin entry points")
    assert _unguarded(values, _guest_sources()) == []


def test_guest_check_fails_on_zero_plugins() -> None:
    with pytest.raises(AssertionError, match=re.escape(f"no {ENTRY_POINT_GROUP} entry points")):
        _unguarded([], ["e_agent.erp"])


def test_guest_check_reports_an_unlisted_plugin() -> None:
    assert _unguarded(["e_agent.plugins.crm.acme.plugin:create_plugin"], ["e_agent.erp"]) == [
        "e_agent.plugins.crm.acme"
    ]
