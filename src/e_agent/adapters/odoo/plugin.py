"""Plugin factory: binds the Odoo executor with host-scoped credentials."""

from __future__ import annotations

from e_agent.sdk.ports import PluginContribution, PluginServices

from .client import OdooJson2Client
from .executor import OdooExecutor


def create_plugin(services: PluginServices) -> PluginContribution:
    settings = services.settings
    if services.credentials is None:
        raise ValueError("odoo19 requires host credentials")
    client = OdooJson2Client(
        str(settings["base_url"]),
        str(settings["database"]),
        timeout=float(str(settings.get("timeout_seconds", "20"))),
        target={
            "database": str(settings["database"]),
            "company_id": str(settings["expected_company_id"]),
            "sandbox_marker": str(settings["expected_sandbox_marker"]),
            "bridge_version": str(settings["expected_bridge_version"]),
        },
    )
    executor = OdooExecutor(client, services.credentials, str(settings["namespace"]))
    return PluginContribution(executors=(executor,))
