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
from urllib.parse import urlsplit

from e_agent.contracts.connection import ConnectionOwnership
from e_agent.plugins.erp.odoo.client import OdooJson2Client
from e_agent.sdk.auth import AuthContext, Secret


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["seed", "seed-tasks", "reset", "info"])
    parser.add_argument("--namespace", default="e-agent-demo")
    parser.add_argument(
        "--scenario", default="valid", choices=["valid", "zero-shortage", "over-budget"]
    )
    parser.add_argument("--expected-marker")
    parser.add_argument("--expected-company-id")
    parser.add_argument("--expected-bridge-version", default="19.0.0.4.0")
    args = parser.parse_args()
    url, db = os.environ["E_AGENT_ODOO_URL"], os.environ["E_AGENT_ODOO_DB"]
    target_url = urlsplit(url)
    if (
        target_url.scheme != "http"
        or target_url.hostname not in {"localhost", "127.0.0.1"}
        or target_url.port != 8069
        or target_url.path not in {"", "/"}
        or target_url.query
        or target_url.fragment
        or target_url.username
    ):
        parser.error("only the authorized loopback learning sandbox on port 8069 is allowed")
    if args.action != "info" and (not args.expected_marker or not args.expected_company_id):
        parser.error("mutations require the explicitly approved marker and company id")
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
    info = await client.call(auth, "e_agent.bridge", "sandbox_info")
    if args.action == "info":
        result = info
    else:
        target = {
            "database": db,
            "company_id": args.expected_company_id,
            "sandbox_marker": args.expected_marker,
            "bridge_version": args.expected_bridge_version,
        }
        if any(info.get(k) != v for k, v in target.items()):
            parser.error("sandbox preflight identity mismatch; no seed or reset was dispatched")
        client = OdooJson2Client(url, db, target=target)
        if args.action == "seed-tasks":
            result = await client.call(
                auth, "e_agent.bridge", "sandbox_seed_tasks", namespace=args.namespace
            )
        elif args.action == "seed":
            result = await client.call(
                auth,
                "e_agent.bridge",
                "sandbox_seed",
                namespace=args.namespace,
                scenario=args.scenario,
            )
        else:
            result = await client.call(
                auth, "e_agent.bridge", "sandbox_reset", namespace=args.namespace
            )
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
