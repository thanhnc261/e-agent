"""Public extension surface of e-agent: ports, manifests and plugin lifecycle."""

SDK_API_VERSION = "1.2"
"""1.1 (ADR 0025): `ProposePlan` and `DriverInput.allowed_capabilities`, both additive.
1.2 (ADRs 0030, 0032): `CapabilityDescriptor.data_classes` and
`PluginContribution.output_schemas` (Task 3b.3), then `DriverInput.context` and
`DriverInput.grounding`; every addition has an empty default."""
ENTRY_POINT_GROUP = "e_agent.plugins.v1"
MANIFEST_FILENAME = "e_agent_plugin.json"

__all__ = ["ENTRY_POINT_GROUP", "MANIFEST_FILENAME", "SDK_API_VERSION"]
