"""Independent-artifact gate (MVP design §13).

Builds every distribution, then for each one creates a clean virtualenv OUTSIDE
the workspace, installs only that wheel plus its declared dependency closure
(first-party wheels from dist/, third-party from the index) and runs a smoke
check from a neutral working directory. Finally runs the fixture demo from the
installed server wheel to prove resources load without the repository.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from plugin_inventory import inventory

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PACKAGES = {
    "e-agent-contracts": (
        "from importlib.resources import files; import e_agent.contracts.digest as d; "
        "files('e_agent.contracts').joinpath('golden/digest_vectors.json').read_text()"
    ),
    # httpx comes only with the [http] extra (Task 1d.7b).
    "e-agent-plugin-sdk": (
        "import importlib.util, e_agent.sdk.discovery, e_agent.sdk.ports; "
        "assert importlib.util.find_spec('httpx') is None, 'bare plugin-sdk installs httpx'"
    ),
    "e-agent-kernel": "import e_agent.kernel.coordinator, e_agent.kernel.registry",
    "e-agent-domain-erp": (
        "from e_agent.sdk.discovery import discover; "
        "ps = [p for p in discover() if p.manifest.plugin_id == 'domain-erp']; "
        "assert ps, 'domain-erp not discoverable from installed wheel'; "
        "from importlib.resources import files; "
        "files('e_agent.erp').joinpath('procurement/rules/inventory.json').read_text(); "
        "files('e_agent.erp').joinpath('procurement/shapes/procurement-shapes.ttl').read_text(); "
        "[files('e_agent.erp').joinpath(p).read_text() for p in ("
        "'procurement/shapes/amend-shapes.ttl', 'sales/shapes/quotation-shapes.ttl', "
        "'crm/shapes/lead-shapes.ttl', 'receivables/rules/inventory.json')]; "
        # The simulator ships in its own wheel since Task 1d.5.
        "assert not any(files('e_agent.erp').joinpath('testing', f).is_file() "
        "for f in ('fake_erp.py', 'scenarios.py')), 'domain-erp still ships the simulator'"
    ),
    "e-agent-adapter-shacl": "import e_agent.adapters.shacl",
    "e-agent-adapter-postgres": (
        "from importlib.resources import files; import e_agent.adapters.postgres; "
        "files('e_agent.adapters.postgres').joinpath('migrations/0001_initial.sql').read_text()"
    ),
    "e-agent-adapter-agent-pydantic": "import e_agent.adapters.pydantic_ai",
    "e-agent-adapter-secretstore-local": "import e_agent.adapters.secretstore_local",
    "e-agent-adapter-odoo": (
        "from e_agent.sdk.discovery import discover; "
        "assert [p for p in discover() if p.manifest.plugin_id == 'odoo19']; "
        # The client imports the SDK HTTP helper, whose httpx comes from plugin-sdk[http].
        "import e_agent.adapters.odoo.client"
    ),
    "e-agent-adapter-erp-simulator": (
        "from e_agent.sdk.discovery import discover; "
        "assert [p for p in discover() if p.manifest.plugin_id == 'fixture-erp']"
    ),
    "e-agent-server": "import e_agent.server.cli",
}


def run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"FAILED: {' '.join(cmd)}")
    return result.stdout


def main() -> int:
    shutil.rmtree(DIST, ignore_errors=True)
    for name in PACKAGES:
        run(["uv", "build", "--package", name, "--out-dir", str(DIST), "--wheel"], cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix="e-agent-wheels-") as tmp:
        neutral = Path(tmp)
        for name, smoke in PACKAGES.items():
            venv = neutral / f"venv-{name}"
            run(["uv", "venv", "--quiet", str(venv)])
            python = venv / "bin" / "python"
            run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--quiet",
                    "--no-cache",  # never reuse a stale wheel with the same version
                    "--python",
                    str(python),
                    "--find-links",
                    str(DIST),
                    name,
                ]
            )
            run([str(python), "-c", smoke], cwd=neutral)
            print(f"ok  {name}: installs and imports from its own dependency closure")
        server_python = neutral / "venv-e-agent-server" / "bin" / "python"
        # The fixture profile enables the simulator, which the server does not depend on.
        run(
            [
                "uv",
                "pip",
                "install",
                "--quiet",
                "--no-cache",
                "--python",
                str(server_python),
                "--find-links",
                str(DIST),
                "e-agent-adapter-erp-simulator",
            ]
        )
        pins = {}
        for stem in ("e_agent_domain_erp", "e_agent_adapter_odoo", "e_agent_adapter_erp_simulator"):
            item = inventory(next(DIST.glob(stem + "-*.whl")))
            pins[item["plugin_id"]] = item["artifact_sha256"]
        run(
            [
                str(server_python),
                "-c",
                (
                    "import json, sys\n"
                    "from e_agent.sdk.discovery import discover, artifact_digest\n"
                    "expected = json.loads(sys.argv[1])\n"
                    "found = {p.manifest.plugin_id: p for p in discover()}\n"
                    "for plugin, pin in expected.items():\n"
                    "    assert artifact_digest(found[plugin].artifact_files) == pin, plugin\n"
                ),
                json.dumps(pins),
            ],
            cwd=neutral,
        )
        print("ok  installed plugin bytes match trusted wheel inventories before activation")
        # The server ships no profile; the fixture profile is a resource of the installed simulator.
        fixture = run(
            [
                str(server_python),
                "-c",
                "from e_agent.plugins.erp.simulator import fixture_profile_path as p; print(p())",
            ],
            cwd=neutral,
        ).strip()
        if not Path(fixture).resolve().is_relative_to(neutral.resolve()):
            raise SystemExit(f"FAILED: fixture profile not from the installed wheel: {fixture}")
        cli = [str(server_python), "-m", "e_agent.server.cli", "--profile", fixture]
        out = run([*cli, "demo", "--json", "--approve"], cwd=neutral)
        state = json.loads(out)["run"]["state"]
        if state != "SUCCEEDED":
            raise SystemExit(f"FAILED: installed demo ended in {state}")
        print("ok  installed e-agent demo completes outside the repository")
        for task in ("amend-rfq", "quotation", "crm-lead", "late-orders", "overdue-invoices"):
            out = run([*cli, "demo", "--json", "--approve", "--task", task], cwd=neutral)
            if json.loads(out)["run"]["state"] != "SUCCEEDED":
                raise SystemExit(f"FAILED: installed {task} demo")
        print("ok  installed ERP-04..08 demos complete outside the repository")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
