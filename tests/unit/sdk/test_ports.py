"""The driver port's plan step and the SDK API version (ADR 0025, Task 2c.7).

`ProposePlan` and `DriverInput.allowed_capabilities` share one additive minor bump of the
SDK API, `1.0` to `1.1`; every manifest in the repository must still admit it.
"""

from pathlib import Path
from typing import get_args

from e_agent.contracts.plan import ActionPlan, ActionProposal, LineageRef, PlannedStep
from e_agent.sdk import MANIFEST_FILENAME, SDK_API_VERSION
from e_agent.sdk.manifest import PluginManifest
from e_agent.sdk.ports import DriverStep, ProposeAction, ProposePlan

PLUGINS = Path(__file__).resolve().parents[3] / "src" / "e_agent" / "plugins"


def test_sdk_api_version_is_the_plan_minor_bump() -> None:
    assert SDK_API_VERSION == "1.1"


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
