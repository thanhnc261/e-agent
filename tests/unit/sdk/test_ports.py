"""The driver port's plan step and the SDK API version (ADR 0025, Task 2c.7; ADR 0032).

`ProposePlan` and `DriverInput.allowed_capabilities` shared one additive minor bump of the
SDK API, `1.0` to `1.1`. Phase 3 makes one more additive bump, `1.1` to `1.2`:
`CapabilityDescriptor.data_classes` and `PluginContribution.output_schemas` (Task 3b.3),
then `DriverInput.context` and `DriverInput.grounding`. Every manifest in the repository
must still admit it.
"""

from pathlib import Path
from typing import get_args

from e_agent.contracts.plan import ActionPlan, ActionProposal, LineageRef, PlannedStep
from e_agent.sdk import MANIFEST_FILENAME, SDK_API_VERSION
from e_agent.sdk.manifest import PluginManifest
from e_agent.sdk.ports import DriverStep, ProposeAction, ProposePlan

PLUGINS = Path(__file__).resolve().parents[3] / "src" / "e_agent" / "plugins"


def test_sdk_api_is_1_2() -> None:
    assert SDK_API_VERSION == "1.2"


def test_sdk_1_2_additions_have_empty_defaults() -> None:
    """A 1.1 plugin's declaration and contribution still load unchanged."""
    from e_agent.contracts.capability import CapabilityDescriptor, EffectKind
    from e_agent.sdk.ports import PluginContribution

    cap = CapabilityDescriptor(
        contract_id="notes.note.read.v1",
        effect=EffectKind.READ,
        input_schema_id="q",
        output_schema_id="n",
    )
    assert cap.data_classes == {}
    assert PluginContribution().output_schemas == {}


def test_plugin_contribution_keeps_its_1_1_positional_order() -> None:
    """C3-2: 1.2 appends ``output_schemas``, so a 1.1 positional call keeps its meaning."""
    from e_agent.sdk.ports import PluginContribution

    built = PluginContribution((), (), (), (), (), {"q": {}}, "guidance")
    assert built.input_schemas == {"q": {}}
    assert built.agent_guidance == "guidance"
    assert built.output_schemas == {}


def test_sdk_api_range_admits_existing_plugins() -> None:
    manifests = sorted(PLUGINS.rglob(MANIFEST_FILENAME))
    checked = 0
    for path in manifests:
        manifest = PluginManifest.model_validate_json(path.read_text(encoding="utf-8"))
        assert manifest.supports_sdk(SDK_API_VERSION), (path, manifest.sdk_api)
        checked += 1
    print(f"plugin manifests admitting sdk_api {SDK_API_VERSION}: {checked}")
    assert checked > 0  # an empty glob is a failure, not a pass (PR-31)


def test_propose_plan_is_a_driver_step() -> None:
    assert ProposePlan in get_args(DriverStep)
    assert ProposeAction in get_args(DriverStep)
    first = ActionProposal(contract_id="notes.note.create.v1", connection_id="c", arguments={})
    second = ActionProposal(
        contract_id="notes.note.create.v1",
        connection_id="c",
        arguments={"parent": LineageRef(step_id="a", path="/key")},
    )
    plan = ActionPlan(
        plan_id="p",
        task_id="t",
        task_version="1",
        steps=(
            PlannedStep(step_id="a", proposal=first),
            PlannedStep(step_id="b", proposal=second, depends_on=("a",)),
        ),
    )
    assert ProposePlan(plan=plan).plan is plan
