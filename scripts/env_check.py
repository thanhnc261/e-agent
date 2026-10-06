"""I00 environment qualification: READ-ONLY checks of the local environment.

Run on the developer machine (not in CI). It never writes to Odoo, PostgreSQL or
Ollama and never prints secrets. Output is a JSON environment manifest for
docs/runbooks/i00-environment-qualification.md.

Inputs come from environment variables:
  E_AGENT_ODOO_URL        e.g. http://localhost:8069 (the odoo19-learning stack, NOT odoo-bench)
  E_AGENT_ODOO_DB         Odoo database name
  E_AGENT_ODOO_API_KEY    API key of the dedicated integration user (never printed)
  E_AGENT_PG_DSN          optional, e-agent's OWN PostgreSQL (must differ from Odoo's DB)
  E_AGENT_OLLAMA_URL      default http://localhost:11434
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

FORBIDDEN_PORTS = {"8071"}  # odoo-bench; never a development target


def _http(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode() or "null"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return 0, {"error": type(exc).__name__}


def check_odoo() -> dict[str, Any]:
    url = os.environ.get("E_AGENT_ODOO_URL", "").rstrip("/")
    db = os.environ.get("E_AGENT_ODOO_DB")
    key = os.environ.get("E_AGENT_ODOO_API_KEY")
    result: dict[str, Any] = {"url": url or None, "database": db}
    if not url:
        result["status"] = "not-configured"
        return result
    if any(url.endswith(f":{p}") for p in FORBIDDEN_PORTS):
        result["status"] = "refused: benchmark instance"
        return result
    status, version = _http(
        f"{url}/web/webclient/version_info", method="POST", body={"jsonrpc": "2.0", "params": {}}
    )
    result["version_info"] = (version or {}).get("result") if status == 200 else None
    if not (db and key):
        result["json2"] = "skipped: database or API key not provided"
        return result
    headers = {"Authorization": f"bearer {key}", "X-Odoo-Database": db}
    status, me = _http(
        f"{url}/json/2/res.users/context_get", method="POST", body={}, headers=headers
    )
    result["json2_context_get_status"] = status
    if status == 200 and isinstance(me, dict):
        result["integration_user_context"] = {k: me.get(k) for k in ("lang", "tz", "uid")}
    status, mods = _http(
        f"{url}/json/2/ir.module.module/search_read",
        method="POST",
        body={"domain": [["state", "=", "installed"]], "fields": ["name"]},
        headers=headers,
    )
    if status == 200 and isinstance(mods, list):
        names = sorted(m["name"] for m in mods)
        result["installed_modules_count"] = len(names)
        result["relevant_modules"] = [
            m
            for m in names
            if m in {"purchase", "stock", "sale_management", "crm", "account", "e_agent_bridge"}
        ]
    status, marker = _http(
        f"{url}/json/2/ir.config_parameter/search_read",
        method="POST",
        body={"domain": [["key", "=", "e_agent.sandbox_marker"]], "fields": ["value"]},
        headers=headers,
    )
    result["sandbox_marker_present"] = bool(status == 200 and marker)
    return result


def check_ollama() -> dict[str, Any]:
    url = os.environ.get("E_AGENT_OLLAMA_URL", "http://localhost:11434").rstrip("/")
    _, version = _http(f"{url}/api/version")
    status, tags = _http(f"{url}/api/tags")
    models = (
        [
            {"name": m.get("name"), "digest": m.get("digest"), "size": m.get("size")}
            for m in (tags or {}).get("models", [])
        ]
        if status == 200
        else []
    )
    return {"url": url, "version": (version or {}).get("version"), "models": models}


def check_postgres() -> dict[str, Any]:
    dsn = os.environ.get("E_AGENT_PG_DSN")
    if not dsn:
        return {"status": "not-configured"}
    odoo_db = os.environ.get("E_AGENT_ODOO_DB")
    if odoo_db and f"/{odoo_db}" in dsn:
        return {"status": "refused: e-agent must not use the Odoo database"}
    return {"status": "configured (connectivity is verified in I05)"}


def main() -> int:
    manifest = {
        "odoo": check_odoo(),
        "ollama": check_ollama(),
        "postgres": check_postgres(),
        "python": sys.version.split()[0],
    }
    json.dump(manifest, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
