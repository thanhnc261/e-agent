"""Execute bridge guard bodies with synthetic metadata; this is not an Odoo ORM test."""

import ast
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

BRIDGE = Path(__file__).resolve().parents[2] / "addons/e_agent_bridge/models/bridge.py"


class Rejected(Exception):
    pass


def method(name, path=BRIDGE):
    tree = ast.parse(path.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    node = next(
        node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name
    )
    node.decorator_list = []
    namespace = {"UserError": Rejected, "MARKER": "e_agent.sandbox_marker", "re": re}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(BRIDGE), "exec"), namespace)
    return namespace[name]


class Metadata:
    def __init__(self, marker, version):
        self.marker, self.latest_version = marker, version

    def sudo(self):
        return self

    def search(self, *args, **kwargs):
        return self

    def get_param(self, name):
        return self.marker


class Env:
    def __init__(self, expected):
        self.context = {"e_agent_target": expected}
        self.cr = SimpleNamespace(dbname="synthetic")
        self.company = SimpleNamespace(id=7)
        self.metadata = Metadata("owned", "19.0.0.3.0")

    def __getitem__(self, model):
        return self.metadata


@pytest.mark.parametrize("field", ["database", "company_id", "sandbox_marker", "bridge_version"])
def test_write_target_guard_rejects_identity_changed_after_preflight(field):
    target = {
        "database": "synthetic",
        "company_id": "7",
        "sandbox_marker": "owned",
        "bridge_version": "19.0.0.3.0",
    }
    target[field] = "different"
    host = SimpleNamespace(env=Env(target), _check=lambda: None)
    with pytest.raises(Rejected, match="TARGET_MISMATCH"):
        method("_check_target")(host)


def test_missing_target_cannot_be_authorized_by_a_marker_alone():
    host = SimpleNamespace(env=Env({}), _check=lambda: None)
    with pytest.raises(Rejected, match="TARGET_REQUIRED"):
        method("_check_target")(host)


@pytest.mark.parametrize("ids", [[2], [1, 1]])
def test_seed_cannot_adopt_unowned_or_ambiguous_existing_records(ids):
    rows = [SimpleNamespace(id=identifier) for identifier in ids]

    class Records:
        def with_context(self, **kwargs):
            return self

        def search(self, *args, **kwargs):
            return rows

    host = SimpleNamespace(env={"res.partner": Records()})
    fixture = SimpleNamespace(inventory={"res.partner": [1]})
    with pytest.raises(Rejected, match="unowned"):
        method("_seed_lookup")(host, fixture, "res.partner", [])


@pytest.mark.parametrize("namespace", ["", "other-owner", "e-agent-%", "e-agent-../"])
def test_seed_and_reset_require_an_explicit_bounded_synthetic_namespace(namespace):
    with pytest.raises(Rejected, match="synthetic namespace"):
        method("_fixture")(SimpleNamespace(), namespace, create=True)


@pytest.mark.parametrize(
    ("filename", "name", "arguments"),
    [
        ("bridge.py", "read_demand", ["synthetic"]),
        ("bridge.py", "read_availability", ["synthetic"]),
        ("bridge.py", "read_offers", ["synthetic"]),
        ("bridge.py", "read_operation", ["synthetic", "operation"]),
        ("bridge_tasks.py", "read_draft_rfq", ["synthetic"]),
        ("bridge_tasks.py", "read_pricing", ["synthetic", "synthetic"]),
        ("bridge_tasks.py", "read_open_orders", ["2026-10-07"]),
        ("bridge_tasks.py", "read_contact", ["synthetic"]),
        ("bridge_tasks.py", "read_teams", []),
        ("bridge_tasks.py", "read_open_invoices", ["2026-10-07"]),
    ],
)
def test_scoped_reads_reject_a_changed_target_before_accessing_business_data(
    filename, name, arguments
):
    def target_changed():
        raise Rejected("TARGET_MISMATCH")

    host = SimpleNamespace(_check_target=target_changed)
    with pytest.raises(Rejected, match="TARGET_MISMATCH"):
        method(name, BRIDGE.with_name(filename))(host, *arguments)
