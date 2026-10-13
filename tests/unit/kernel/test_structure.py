"""The coordinator's import surface, pinned before the Phase 1 kernel split (plan Task 1c.1).

The split moves methods into mixin modules verbatim. These tests keep every
name that tests, scripts and the server import from `e_agent.kernel.coordinator`
importable from there, and every method they call reachable on `RunCoordinator`.
"""

import importlib
import inspect
import logging
import tomllib
from pathlib import Path

import pytest

coordinator = importlib.import_module("e_agent.kernel.coordinator")

# Imported by name outside the module (server bootstrap, kernel tests) or used
# by the moved code and re-exported for compatibility.
MODULE_NAMES = [
    "RunCoordinator",
    "_Continuation",
    "_GatewayReader",
    "CONTINUATION_SCHEMA",
    "DEFAULT_APPROVAL_TTL",
    "LOG",
]

PUBLIC_METHODS = [
    "start_run",
    "admit_run",
    "start_admitted_run",
    "set_text_sink",
    "release_continuation",
    "get_run",
    "accept_input",
    "continue_input",
    "resume_input",
    "pending_approval",
    "sweep_expired_approvals",
    "expire_approval",
    "decide",
    "reconcile",
    "cancel",
    "recover",
    "recover_run",
]

# Private methods that tests call, read or monkeypatch on a coordinator instance.
PRIVATE_METHODS_USED_BY_TESTS = ["_peek_cont", "_set_run_state", "_gateway_read"]


@pytest.mark.parametrize("name", MODULE_NAMES)
def test_coordinator_module_keeps_its_import_names(name: str) -> None:
    assert hasattr(coordinator, name)


@pytest.mark.parametrize("name", PUBLIC_METHODS + PRIVATE_METHODS_USED_BY_TESTS)
def test_run_coordinator_keeps_its_methods(name: str) -> None:
    method = getattr(coordinator.RunCoordinator, name)
    assert inspect.isfunction(method)


def test_coordinator_log_keeps_its_logger_name() -> None:
    assert coordinator.LOG is logging.getLogger("e_agent.kernel.coordinator")


KERNEL = Path(coordinator.__file__).resolve().parent
MAX_KERNEL_MODULE_LINES = 500
FACADE_CONTRACT = "Only the facade module imports e_agent.kernel.coordinator"


def test_each_method_defined_once() -> None:
    homes: dict[str, list[str]] = {}
    for cls in coordinator.RunCoordinator.__mro__[:-1]:  # without object
        for name, value in vars(cls).items():
            if inspect.isfunction(value):
                homes.setdefault(name, []).append(cls.__name__)
    shadowed = {name: owners for name, owners in homes.items() if len(owners) > 1}
    assert shadowed == {}


@pytest.mark.parametrize("module", sorted(p.name for p in KERNEL.glob("*.py")))
def test_kernel_module_size(module: str) -> None:
    lines = (KERNEL / module).read_text(encoding="utf-8").count("\n")
    assert lines <= MAX_KERNEL_MODULE_LINES, f"{module}: {lines} lines"


def test_facade_import_contract_covers_every_other_kernel_module() -> None:
    config = tomllib.loads((KERNEL.parents[2] / "pyproject.toml").read_text(encoding="utf-8"))
    [contract] = [
        c for c in config["tool"]["importlinter"]["contracts"] if c["name"] == FACADE_CONTRACT
    ]
    assert contract["forbidden_modules"] == ["e_agent.kernel.coordinator"]
    modules = {f"e_agent.kernel.{p.stem}" for p in KERNEL.glob("*.py") if p.stem != "__init__"}
    assert set(contract["source_modules"]) == modules - {"e_agent.kernel.coordinator"}
