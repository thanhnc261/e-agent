"""The coordinator's import surface, pinned before the Phase 1 kernel split (plan Task 1c.1).

The split moves methods into mixin modules verbatim. These tests keep every
name that tests, scripts and the server import from `e_agent.kernel.coordinator`
importable from there, and every method they call reachable on `RunCoordinator`.
"""

import importlib
import inspect
import logging

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
