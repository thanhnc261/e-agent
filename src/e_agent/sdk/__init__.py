"""Public extension surface of e-agent: ports, manifests and plugin lifecycle."""

SDK_API_VERSION = "1.1"
"""1.1 (ADR 0025): `ProposePlan` and `DriverInput.allowed_capabilities`, both additive."""
ENTRY_POINT_GROUP = "e_agent.plugins.v1"
MANIFEST_FILENAME = "e_agent_plugin.json"

__all__ = ["ENTRY_POINT_GROUP", "MANIFEST_FILENAME", "SDK_API_VERSION"]
