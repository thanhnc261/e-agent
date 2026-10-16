"""Core-only install gate (roadmap Phase 1d, Task 1d.8, decision D3).

Builds the core wheels and a throwaway non-ERP test pack, installs them into a
fresh virtualenv OUTSIDE the workspace without any ERP wheel, checks that no ERP
distribution or package arrived, then starts the installed server with a profile
that enables only the test pack and asks ``/health/ready``.

The helpers are pure and importable; tests/conformance/test_core_only.py checks
them without building wheels. Wheels go to a temporary directory, never dist/.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent.parent
DISTS = ROOT / "dists"

CORE_DISTRIBUTIONS = (
    "e-agent-contracts",
    "e-agent-plugin-sdk",
    "e-agent-kernel",
    "e-agent-server",
    "e-agent-adapter-shacl",
    "e-agent-adapter-postgres",
    "e-agent-adapter-agent-pydantic",
    "e-agent-adapter-secretstore-local",
)
ERP_DISTRIBUTIONS = frozenset(
    {"e-agent-domain-erp", "e-agent-adapter-odoo", "e-agent-adapter-erp-simulator", "e-agent-erp"}
)
ERP_MODULES = ("e_agent.erp", "e_agent.adapters.odoo", "e_agent.plugins.erp")

PACK_DISTRIBUTION = "core-test-pack"
PACK_VERSION = "0.1.0"
PACK_PLUGIN_ID = "core-test-pack"
PACK_PACKAGE = "core_test_pack"
PACK_FACTORY = f"{PACK_PACKAGE}.plugin:create_plugin"
PACK_ENTRY_POINT = "core-test-pack"
PRESET_KIND = "core-note"
DRIVER_KIND = "scripted"
TENANT = "tenant-core"
CONNECTION = "conn-core-notes"
INTEGRATION = "core-notes"
READ_CONTRACT = "corenotes.note.read.v1"
READ_BINDING = f"{INTEGRATION}.read"

ENTRY_POINT_GROUP = "e_agent.plugins.v1"  # e_agent.sdk.ENTRY_POINT_GROUP
MANIFEST_FILENAME = "e_agent_plugin.json"  # e_agent.sdk.MANIFEST_FILENAME
READY_TIMEOUT_S = 60.0

# A self-contained notes-like domain: one read-only capability, its executor, a
# task preset and a scripted driver. It imports only e_agent.contracts and e_agent.sdk.
PACK_MODULE_SOURCE = f'''"""Throwaway non-ERP pack for scripts/check_core_only.py."""

from __future__ import annotations

from dataclasses import dataclass

from e_agent.contracts.capability import CapabilityDescriptor, EffectKind
from e_agent.contracts.common import new_id, utc_now
from e_agent.contracts.evidence import EvidenceRef
from e_agent.sdk.errors import KnownNoEffectError
from e_agent.sdk.ports import (
    DriverRequest,
    FinalAnswer,
    Observation,
    PluginContribution,
    ReadRequest,
    RequestReads,
    TaskPreset,
)

READ = CapabilityDescriptor(
    contract_id={READ_CONTRACT!r},
    effect=EffectKind.READ,
    input_schema_id="q",
    output_schema_id="n",
)


class NotesBackend:
    def supports(self, binding):
        return binding.plugin_id == {PACK_PLUGIN_ID!r}

    async def read(self, ctx, binding, request):
        evidence = EvidenceRef(
            evidence_id=new_id("ev"),
            tenant_id=ctx.tenant_id,
            source="core-notes",
            locator="all",
            revision="rev:1",
            observed_at=utc_now(),
            scope=ctx.tenant_id,
        )
        return Observation(
            request_id=request.request_id,
            contract_id=request.contract_id,
            data={{"topic": "core", "count": "0"}},
            evidence=evidence,
        )

    async def execute(self, ctx, binding, action, attempt):
        raise KnownNoEffectError("READ_ONLY", "the core test pack has no writes")

    async def reconcile(self, ctx, binding, action):
        return None


@dataclass
class NotesDriver:
    connection_id: str
    driver_id: str = "core-notes-driver"

    async def advance(self, ctx, step_input):
        if not step_input.observations:
            return RequestReads(
                reads=(
                    ReadRequest(
                        request_id="r1",
                        contract_id=READ.contract_id,
                        connection_id=self.connection_id,
                        arguments={{}},
                    ),
                )
            )
        return FinalAnswer(text="no notes yet")


def _driver(request: DriverRequest) -> NotesDriver:
    return NotesDriver(connection_id=request.connection_id)


def create_plugin(services):
    return PluginContribution(
        capabilities=(READ,),
        executors=(NotesBackend(),),
        task_presets=(TaskPreset(kind={PRESET_KIND!r}, prompt="summarize the core notes"),),
        driver_factories={{{DRIVER_KIND!r}: _driver}},
    )
'''


def pack_manifest() -> dict[str, Any]:
    return {
        "plugin_id": PACK_PLUGIN_ID,
        "version": PACK_VERSION,
        "sdk_api": ">=1.0,<2.0",
        "factory": PACK_FACTORY,
        "kind": "domain",
        "provides_capabilities": [
            {
                "contract_id": READ_CONTRACT,
                "effect": "read",
                "input_schema_id": "q",
                "output_schema_id": "n",
            }
        ],
        "provides_bindings": [{"binding_id": READ_BINDING, "contract_id": READ_CONTRACT}],
    }


def pack_pyproject() -> str:
    return (
        "[project]\n"
        f'name = "{PACK_DISTRIBUTION}"\n'
        f'version = "{PACK_VERSION}"\n'
        'requires-python = ">=3.12"\n'
        'dependencies = ["e-agent-contracts>=0.1,<0.2", "e-agent-plugin-sdk>=0.1,<0.2"]\n'
        "\n"
        f'[project.entry-points."{ENTRY_POINT_GROUP}"]\n'
        f'{PACK_ENTRY_POINT} = "{PACK_FACTORY}"\n'
        "\n"
        "[build-system]\n"
        'requires = ["hatchling>=1.32,<2"]\n'
        'build-backend = "hatchling.build"\n'
        "\n"
        "[tool.hatch.build.targets.wheel]\n"
        f'packages = ["{PACK_PACKAGE}"]\n'
    )


def pack_package_files() -> dict[str, str]:
    """The pack's package files, keyed by their path relative to the import root."""
    return {
        f"{PACK_PACKAGE}/__init__.py": "",
        f"{PACK_PACKAGE}/plugin.py": PACK_MODULE_SOURCE,
        f"{PACK_PACKAGE}/{MANIFEST_FILENAME}": json.dumps(pack_manifest(), indent=2) + "\n",
    }


def write_pack_project(root: Path) -> Path:
    """Write the hatchling project of the test pack under ``root``; return its directory."""
    project = root / PACK_DISTRIBUTION
    for relative, text in pack_package_files().items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, "utf-8")
    (project / "pyproject.toml").write_text(pack_pyproject(), "utf-8")
    return project


def core_profile() -> dict[str, Any]:
    """A fixture profile that enables only the test pack and names its preset."""
    return {
        "profile_version": "1",
        "environment": "fixture",
        "tenant_id": TENANT,
        "operator": {"principal_id": "core-operator", "roles": ["requester"]},
        "enabled_plugins": {PACK_PLUGIN_ID: {"version": PACK_VERSION}},
        "connections": [
            {
                "tenant_id": TENANT,
                "connection_id": CONNECTION,
                "version": 1,
                "integration_id": INTEGRATION,
                "ownership": "tenant_shared",
                "provider_subject": "svc",
            }
        ],
        "bindings": {b["binding_id"]: [CONNECTION] for b in pack_manifest()["provides_bindings"]},
        "driver": {"kind": DRIVER_KIND, "task_kind": PRESET_KIND},
    }


def dist_projects(dists: Path = DISTS) -> dict[str, dict[str, Any]]:
    """Every distribution's ``[project]`` table, keyed by its canonical name."""
    projects: dict[str, dict[str, Any]] = {}
    for config in sorted(dists.glob("*/pyproject.toml")):
        project = tomllib.loads(config.read_text("utf-8"))["project"]
        projects[canonicalize_name(project["name"])] = project
    if not projects:
        raise ValueError(f"no distributions under {dists}")
    return projects


def core_distributions(dists: Path = DISTS) -> list[str]:
    """Every distribution that is not a named ERP one; an unknown ERP name is an error."""
    names = set(dist_projects(dists))
    missing = ERP_DISTRIBUTIONS - names
    if missing:
        raise ValueError(f"ERP distributions not found under {dists}: {sorted(missing)}")
    return sorted(names - ERP_DISTRIBUTIONS)


def requirement_names(project: dict[str, Any]) -> list[str]:
    """Required and optional dependency names of one ``[project]`` table."""
    specs = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        specs += extra
    return sorted({canonicalize_name(Requirement(spec).name) for spec in specs})


def forbidden_installed(installed: Iterable[str]) -> list[str]:
    """The ERP distributions among ``installed``; an empty list is an error (PR-31)."""
    names = {canonicalize_name(name) for name in installed}
    if not names:
        raise ValueError("no installed distributions listed")
    return sorted(names & ERP_DISTRIBUTIONS)


def locked_constraints(text: str) -> list[str]:
    """Third-party pins from ``uv export``; fails on none or on any first-party entry.

    The core venv installs the versions uv.lock holds, so an upstream release
    cannot turn the gate red without a code change.
    """
    names = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-") or "file:" in line:
            raise ValueError(f"constraint is not a plain pin: {line!r}")
        requirement = Requirement(line)
        name = canonicalize_name(requirement.name)
        if name.startswith("e-agent") or name == PACK_DISTRIBUTION:
            raise ValueError(f"constraints name a first-party distribution: {line!r}")
        if len(requirement.specifier) != 1 or next(iter(requirement.specifier)).operator != "==":
            raise ValueError(f"constraint is not an exact pin: {line!r}")
        names.append(name)
    if not names:
        raise ValueError("no locked third-party constraints exported")
    return sorted(names)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def wait_ready(
    proc: subprocess.Popen[bytes], url: str, log: Path, timeout: float = READY_TIMEOUT_S
) -> dict[str, Any]:
    """Poll ``url`` until it answers; fail at once if ``proc`` exits first."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            output = log.read_text("utf-8", errors="replace") if log.exists() else ""
            raise RuntimeError(f"server exited with {proc.returncode} before ready:\n{output}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                body: dict[str, Any] = json.loads(response.read())
                return body
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.2)
    output = log.read_text("utf-8", errors="replace") if log.exists() else ""
    raise RuntimeError(f"no answer from {url} within {timeout:.0f}s:\n{output}")


# Runs inside the core venv: what is installed and what can be imported.
_INSPECT = """
import importlib.util, json, sys
from importlib import metadata
names = sorted({d.metadata["Name"] for d in metadata.distributions()})
specs = {}
for module in sys.argv[1:]:
    try:
        specs[module] = importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        specs[module] = False
import e_agent.server
print(json.dumps({
    "installed": names,
    "found": specs,
    "server_requires": metadata.requires("e-agent-server") or [],
    "server_file": e_agent.server.__file__,
}))
"""


def run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"FAILED: {' '.join(cmd)}")
    return result.stdout


def fail(message: str) -> None:
    raise SystemExit(f"FAILED: {message}")


def main() -> int:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="e-agent-core-only-") as tmp:
        neutral = Path(tmp)
        wheels = neutral / "wheels"
        for name in CORE_DISTRIBUTIONS:
            run(["uv", "build", "--package", name, "--wheel", "--out-dir", str(wheels)], cwd=ROOT)
        pack = write_pack_project(neutral / "src")
        run(["uv", "build", "--wheel", "--out-dir", str(wheels), str(pack)], cwd=neutral)
        built = sorted(p.name for p in wheels.glob("*.whl"))
        if len(built) != len(CORE_DISTRIBUTIONS) + 1:
            fail(f"expected {len(CORE_DISTRIBUTIONS) + 1} wheels, built {built}")
        print(f"ok  built {len(built)} wheels (core and the test pack) outside dist/")

        constraints = neutral / "constraints.txt"
        export = ["uv", "export", "--frozen", "--no-hashes", "--no-header", "--no-annotate"]
        run([*export, "--no-emit-workspace", "--all-groups", "-o", str(constraints)], cwd=ROOT)
        pins = locked_constraints(constraints.read_text("utf-8"))
        print(f"ok  {len(pins)} third-party versions constrained to uv.lock")

        venv = neutral / "venv"
        run(["uv", "venv", "--quiet", str(venv)])
        python = venv / "bin" / "python"
        first_party = [*CORE_DISTRIBUTIONS, PACK_DISTRIBUTION]
        refresh = [arg for name in first_party for arg in ("--refresh-package", name)]
        install = ["uv", "pip", "install", "--quiet", "--python", str(python), *refresh]
        install += ["-c", str(constraints), "--find-links", str(wheels)]
        run([*install, *first_party], cwd=neutral)

        # -I: no PYTHONPATH, no cwd on sys.path; nothing may come from the repository.
        facts = json.loads(run([str(python), "-I", "-c", _INSPECT, *ERP_MODULES], cwd=neutral))
        installed: list[str] = facts["installed"]
        bad = forbidden_installed(installed)
        if bad:
            fail(f"ERP distributions installed: {bad}")
        missing = {canonicalize_name(n) for n in first_party} - {
            canonicalize_name(n) for n in installed
        }
        if missing:
            fail(f"first-party distributions not installed: {sorted(missing)}")
        found = [m for m in ERP_MODULES if facts["found"].get(m, True)]
        if len(facts["found"]) != len(ERP_MODULES) or found:
            fail(f"ERP packages importable: {found or facts['found']}")
        server_erp = [
            r
            for r in facts["server_requires"]
            if canonicalize_name(Requirement(r).name) in ERP_DISTRIBUTIONS
        ]
        if server_erp:
            fail(f"installed e-agent-server still requires {server_erp}")
        if not Path(facts["server_file"]).resolve().is_relative_to(venv.resolve()):
            fail(f"e_agent.server not imported from the venv: {facts['server_file']}")
        print(
            f"ok  {len(installed)} distributions installed; none of the "
            f"{len(ERP_DISTRIBUTIONS)} ERP distributions, none of the "
            f"{len(ERP_MODULES)} ERP packages importable"
        )

        profile = neutral / "core-profile.json"
        profile.write_text(json.dumps(core_profile(), indent=2), "utf-8")
        port = free_port()
        log = neutral / "server.log"
        cli = [str(python), "-I", "-m", "e_agent.server.cli", "--profile", str(profile)]
        with log.open("wb") as out:
            proc = subprocess.Popen(
                [*cli, "serve", "--port", str(port)],
                cwd=neutral,
                stdout=out,
                stderr=subprocess.STDOUT,
            )
            try:
                ready = wait_ready(proc, f"http://127.0.0.1:{port}/health/ready", log)
            except RuntimeError as exc:
                fail(str(exc))
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        checks = {"status": "ready", "plugins": [PACK_PLUGIN_ID]}
        wrong = {k: ready.get(k) for k, v in checks.items() if ready.get(k) != v}
        if wrong:
            fail(f"/health/ready answered {ready}; expected {checks}")
        print(f"ok  installed server is ready with only {PACK_PLUGIN_ID}: {len(checks)} fields")
    print(f"core-only check passed in {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
