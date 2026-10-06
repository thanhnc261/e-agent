"""Seed or reset the synthetic e-agent fixture in a SANDBOX Odoo (bridge addon).

Requires an administrator API key that is also in the e-agent integration group,
and the e_agent.sandbox_marker system parameter on the target database; the
bridge refuses otherwise. Only records in the given namespace are touched.

    E_AGENT_ODOO_URL=http://localhost:8069 E_AGENT_ODOO_DB=odoo19 \\
    E_AGENT_ODOO_ADMIN_KEY=... uv run python scripts/odoo_sandbox.py seed --namespace demo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from e_agent.adapters.odoo.client import OdooJson2Client
from e_agent.contracts.connection import ConnectionOwnership
from e_agent.sdk.auth import AuthContext, Secret


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["seed", "seed-tasks", "reset", "info"])
    parser.add_argument("--namespace", default="e-agent-demo")
    parser.add_argument(
        "--scenario", default="valid", choices=["valid", "zero-shortage", "over-budget"]
    )
    args = parser.parse_args()
    url, db = os.environ["E_AGENT_ODOO_URL"], os.environ["E_AGENT_ODOO_DB"]
    if url.rstrip("/").endswith(":8071"):
        sys.stderr.write("refusing: port 8071 is the benchmark instance\n")
        return 2
    auth = AuthContext(
        connection_id="admin",
        connection_version=1,
        ownership=ConnectionOwnership.TENANT_SHARED,
        provider_subject="admin",
        method="api_key",
        _secret=Secret(os.environ["E_AGENT_ODOO_ADMIN_KEY"]),
        _placement={"header": "Authorization", "prefix": "bearer "},
    )
    client = OdooJson2Client(url, db)
    if args.action == "info":
        result = await client.call(auth, "e_agent.bridge", "sandbox_info")
    elif args.action == "seed-tasks":  # ERP-04..08 data (also seeds the procurement fixture)
        result = await client.call(
            auth, "e_agent.bridge", "sandbox_seed_tasks", namespace=args.namespace
        )
    elif args.action == "seed":
        result = await client.call(
            auth, "e_agent.bridge", "sandbox_seed", namespace=args.namespace, scenario=args.scenario
        )
    else:
        result = await client.call(
            auth, "e_agent.bridge", "sandbox_reset", namespace=args.namespace
        )
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
