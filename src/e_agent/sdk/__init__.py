"""Public extension surface of e-agent: ports, manifests and plugin lifecycle."""

SDK_API_VERSION = "1.2"
"""1.1 (ADR 0025): `ProposePlan` and `DriverInput.allowed_capabilities`, both additive.
1.2 (ADR 0032 §12), one unreleased additive version, every field with a default:
`CapabilityDescriptor.data_classes` and `PluginContribution.output_schemas` (ADR 0030,
Task 3b.3), `DriverInput.context` (Task 3d.1), `PluginContribution.rule_inventory` (ADR
0009, ADR 0033 §4, Task 3e.3) and `DriverInput.grounding` (ADR 0033, Task 3e.4)."""
ENTRY_POINT_GROUP = "e_agent.plugins.v1"
MANIFEST_FILENAME = "e_agent_plugin.json"

__all__ = ["ENTRY_POINT_GROUP", "MANIFEST_FILENAME", "SDK_API_VERSION"]
