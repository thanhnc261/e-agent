"""The server composes any domain pack, not only ERP (XA-02, ADR 0026, R-7).

The non-ERP notes pack from ``tests/unit/kernel/conftest.py`` is installed as a
discovered plugin and composed through ``build_runtime``; the server source names
no domain.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from e_agent.kernel.connections import ConnectionCatalog
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.sdk.discovery import discover
from e_agent.server.bootstrap import admit_plugins
from e_agent.server.profile import load_profile

from tests.unit.kernel.conftest import BINDINGS, CONN, CREATE, READ, TENANT

REPO = Path(__file__).resolve().parents[3]
SERVER = REPO / "src" / "e_agent" / "server"
ERP_PACKAGES = ("e_agent.plugins.erp",)

_NOTES_PLUGIN = """
from e_agent.sdk.ports import PluginContribution, TaskPreset
from tests.unit.kernel.conftest import (
    CREATE, READ, NotesBackend, NotesValidator, NotesVerifier,
)


def create_plugin(services):
    return PluginContribution(
        capabilities=(READ, CREATE),
        validators=(NotesValidator(),),
        executors=(NotesBackend(),),
        verifiers=(NotesVerifier(),),
        task_presets=(TaskPreset(kind="standup-note", prompt="write standup note"),),
    )
"""

_COMPOSE_AND_RUN = """
import asyncio, json, sys
sys.path.insert(0, sys.argv[1])
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import Profile
from tests.unit.kernel.conftest import NotesDriver

async def main():
    profile = Profile.model_validate(json.loads(sys.argv[2]))
    rt = await build_runtime(
        profile,
        plugin_paths=[sys.argv[1]],
        driver_factory=lambda registry: NotesDriver(texts=["standup notes"]),
    )
    run = await rt.coordinator.start_run(rt.operator, "write standup note", rt.scope)
    events = await rt.store.list_events(profile.tenant_id, run.run_id)
    print(json.dumps({
        "admitted": rt.registry.report.admitted,
        "state": run.state.value,
        "events": [e.type.value for e in events],
        "modules": sorted(sys.modules),
    }))

asyncio.run(main())
"""


def _install_notes_pack(root: Path) -> None:
    """The notes pack as an installed distribution: manifest, entry point, RECORD."""
    pkg = root / "notes_pack"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "plugin.py").write_text(_NOTES_PLUGIN)
    manifest = {
        "plugin_id": "notes-fixture",
        "version": "0.1.0",
        "sdk_api": ">=1.0,<2.0",
        "factory": "notes_pack.plugin:create_plugin",
        "kind": "domain",
        "provides_capabilities": [c.model_dump(mode="json") for c in (READ, CREATE)],
        "provides_bindings": [b.model_dump(mode="json") for b in BINDINGS],
    }
    (pkg / "e_agent_plugin.json").write_text(json.dumps(manifest))
    info = root / "notes_pack-0.1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: notes-pack\nVersion: 0.1.0\n")
    (info / "entry_points.txt").write_text(
        "[e_agent.plugins.v1]\nnotes = notes_pack.plugin:create_plugin\n"
    )
    (info / "RECORD").write_text(
        "notes_pack/__init__.py,,\nnotes_pack/plugin.py,,\nnotes_pack/e_agent_plugin.json,,\n"
    )


def _notes_profile() -> dict[str, Any]:
    return {
        "profile_version": "1",
        "environment": "fixture",
        "tenant_id": TENANT,
        "operator": {"principal_id": "alice", "roles": ["requester"]},
        "enabled_plugins": {"notes-fixture": {"version": "0.1.0"}},
        "connections": [
            {
                "tenant_id": TENANT,
                "connection_id": CONN,
                "version": 1,
                "integration_id": "notes-mem",
                "ownership": "tenant_shared",
                "provider_subject": "svc",
            }
        ],
        "bindings": {b.binding_id: [CONN] for b in BINDINGS},
        "driver": {"task_kind": "standup-note"},
    }


def test_notes_pack_composes_through_bootstrap(tmp_path: Path) -> None:
    _install_notes_pack(tmp_path)
    out = subprocess.run(
        [sys.executable, "-c", _COMPOSE_AND_RUN, str(tmp_path), json.dumps(_notes_profile())],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO,
    ).stdout
    result = json.loads(out)
    assert result["admitted"] == ["notes-fixture"]
    # The driver's read went through the gateway, then its write waits for approval.
    assert "read.recorded" in result["events"], result["events"]
    assert result["state"] == "WAITING_APPROVAL"
    assert "notes_pack.plugin" in result["modules"]
    assert [m for m in result["modules"] if m.startswith(ERP_PACKAGES)] == []


# Ref values (``demand:d-001``) and provider, domain and workflow names. The pre-ADR
# 0026 profile keys ``demand_ref`` and ``product_ref`` are an approved migration
# fold (profile.OLD_REF_KEYS) and match none of these patterns.
_DOMAIN_LITERAL = re.compile(r"demand:|product:|odoo|erp|procure", re.IGNORECASE)


def test_server_has_no_domain_literals() -> None:
    sources = sorted(p for p in SERVER.rglob("*.py") if "__pycache__" not in p.parts)
    assert sources, f"no server sources under {SERVER}"
    hits = [
        f"{path.relative_to(REPO)}:{number}: {line.strip()}"
        for path in sources
        for number, line in enumerate(path.read_text("utf-8").splitlines(), start=1)
        if _DOMAIN_LITERAL.search(line)
    ]
    print(f"scanned {len(sources)} server sources")
    assert hits == []


def test_capabilities_without_requirements_unchanged() -> None:
    # No committed manifest declares features, so the required-features check
    # (XA-03) admits the fixture profile's plugins and bindings as before.
    profile = load_profile(fixture_profile_path())
    registry, _ = admit_plugins(profile, ConnectionCatalog(profile.connections), discover(), None)
    assert registry.report.admitted == ["domain-erp", "fixture-erp"]
    assert registry.report.skipped == ["odoo19"]
    assert sorted((b.binding_id, b.connection_id) for b in registry.bindings) == sorted(
        (binding, conn) for binding, conns in profile.bindings.items() for conn in conns
    )
    assert len(registry.bindings) == 17
    assert len(registry.capabilities) == 21
