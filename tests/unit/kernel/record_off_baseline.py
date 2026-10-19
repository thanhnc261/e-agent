"""Record the off-mode golden event stream of the notes domain (Task 2b.1, ADR 0027).

One run on the kernel as it was before any Phase 2 feature landed: the
notes-domain write run (the domain-neutral fixture in ``conftest.py``). It
records the event types in order with each event's payload key set, the final
run state and its transitions, and every action's state and approval digest
(the key sets were added in Task 2c.5, recorded on the kernel as Task 2c.4 left
it, before any shadow change). ``off`` mode must keep this stream exactly;
``test_off_baseline.py`` asserts against it.

Task 3c.2 (ADR 0031 §4, plan D7) adds payload keys reconstruction needs. The Phase 2
golden above stays frozen and ``test_off_baseline.py`` compares the projection of the
current stream onto its keys (`phase2_projection`); the current stream is recorded beside
it as ``off_mode_events_v3.json``, which ``test_off_projection.py`` asserts and proves the
frozen golden a projection of. The ERP draft-po baseline lives
with the simulator plugin's tests
(``tests/unit/plugins/erp/simulator/record_off_baseline_erp.py``), because the
kernel suite imports no plugin (``tests/conformance/test_kernel_tests_neutral.py``).

Ids come from a deterministic source: ``new_id`` draws its hex from
``uuid.uuid4()`` in ``e_agent.contracts.common``, which is replaced by a counter
for the run, so the digest input (``logical_operation_id``, evidence ids) is
stable. The run uses the in-memory store on purpose: a store that calls
``new_id`` at other points would shift the counter. Generated ids are then
normalised to ``<prefix>#<ordinal of first appearance>``.

Re-record only for a change the plan names:
``uv run python tests/unit/kernel/record_off_baseline.py``. It writes the v3 golden only;
the Phase 2 golden is never re-recorded.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from e_agent.contracts import common
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEventType
from e_agent.kernel.memory_store import InMemoryRunStore
from e_agent.kernel.reconstruct import without_reconstruction_keys

GOLDEN = Path(__file__).parent / "golden" / "off_mode_events.json"
"""The Phase 2 golden: frozen (ADR 0031 §4)."""
GOLDEN_V3 = Path(__file__).parent / "golden" / "off_mode_events_v3.json"
RUNS = ("notes-write",)
_ID = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*?)_([0-9a-f]{32})\b")


@contextmanager
def deterministic_ids() -> Iterator[None]:
    """Make every ``new_id`` call return a counter-based id for the duration."""
    counter = iter(range(1, 1 << 30))
    shim = SimpleNamespace(uuid4=lambda: uuid.UUID(int=next(counter)))
    with mock.patch.object(common, "uuid", shim):
        yield


def _normalise(value: str, seen: dict[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(0)
        if key not in seen:
            prefix = m.group(1)
            ordinal = sum(1 for v in seen.values() if v.startswith(prefix + "#")) + 1
            seen[key] = f"{prefix}#{ordinal}"
        return seen[key]

    return _ID.sub(repl, value)


async def _summarise(store: Any, tenant_id: str, run: Any, digest: str) -> dict[str, Any]:
    seen: dict[str, str] = {}
    events = await store.list_events(tenant_id, run.run_id)
    actions = await store.list_actions(tenant_id, run.run_id)
    return {
        "run_state": str(run.state),
        "approval_digest": digest,
        "event_types": [str(e.type) for e in events],
        # Each event's payload key set, so an off-mode change to a payload alone is caught.
        "payload_keys": [sorted(e.payload) for e in events],
        "run_transitions": [
            str(e.payload.get("to")) for e in events if e.type == RunEventType.RUN_STATE_CHANGED
        ],
        "actions": [
            {
                "action_id": _normalise(a.action_id, seen),
                "contract_id": a.contract_id,
                "state": str(a.state),
                "digest": a.digest,
            }
            for a in actions
        ],
    }


async def notes_write_run() -> dict[str, Any]:
    """The notes-domain happy path: read, propose, approve, dispatch, verify."""
    from e_agent.contracts.connection import ConnectionDescriptor, ConnectionOwnership
    from e_agent.kernel.connections import ConnectionCatalog
    from e_agent.kernel.coordinator import RunCoordinator
    from e_agent.kernel.policy import DefaultPolicy
    from e_agent.kernel.registry import PluginRegistry
    from e_agent.sdk.ports import PluginContribution

    from tests.unit.kernel.conftest import (
        BINDINGS,
        CONN,
        CREATE,
        NOTES_TASK,
        READ,
        TENANT,
        Clock,
        NotesBackend,
        NotesDriver,
        NotesValidator,
        NotesVerifier,
        principal,
    )

    with deterministic_ids():
        backend, validator, verifier = NotesBackend(), NotesValidator(), NotesVerifier()
        registry = PluginRegistry({b.binding_id: (CONN,) for b in BINDINGS})
        registry.register(
            plugin_id="notes-fixture",
            plugin_version="0.1.0",
            declared_capabilities=(READ, CREATE),
            binding_templates=BINDINGS,
            contribution=PluginContribution(
                capabilities=(READ, CREATE),
                validators=(validator,),
                executors=(backend,),
                verifiers=(verifier,),
            ),
        )
        catalog = ConnectionCatalog(
            [
                ConnectionDescriptor(
                    tenant_id=TENANT,
                    connection_id=CONN,
                    version=1,
                    integration_id="notes-mem",
                    ownership=ConnectionOwnership.TENANT_SHARED,
                    provider_subject="svc",
                )
            ]
        )
        store = InMemoryRunStore()
        coordinator = RunCoordinator(
            store=store,
            registry=registry,
            connections=catalog,
            policy=DefaultPolicy(),
            driver=NotesDriver(texts=["standup notes"]),
            clock=Clock(),
        )
        requester = principal("alice", {"requester"})
        approver = principal("bob", {"approver"})
        # The task kind, as the CLI passes it (Task 2c.5): ``off`` ignores it.
        run = await coordinator.start_run(
            requester, "write standup note", frozenset({CONN}), task_kind=NOTES_TASK.task_id
        )
        pres = await coordinator.pending_approval(TENANT, run.run_id)
        run = await coordinator.decide(
            actor=approver,
            run_id=run.run_id,
            action_id=pres.action_id,
            action_digest=pres.digest,
            expected_run_revision=pres.run_revision,
            decision=ApprovalDecision.APPROVED,
        )
        return await _summarise(store, TENANT, run, pres.digest)


async def record_baseline() -> dict[str, Any]:
    return {"notes-write": await notes_write_run()}


def assert_matches(golden: dict[str, Any], actual: dict[str, Any]) -> int:
    """Compare every recorded run; refuse a golden with no runs or no events (ENG-EVID-4)."""
    cases = [name for name, run in golden.items() if run.get("event_types")]
    if not cases or len(cases) != len(golden):
        raise AssertionError(f"off-mode golden has {len(cases)} cases with events; refusing")
    for name in cases:
        assert actual.get(name) == golden[name], f"off-mode stream changed for {name}"
    assert set(actual) == set(golden), "off-mode runs differ from the golden"
    print(f"off-mode baseline: {len(cases)} cases matched")
    return len(cases)


def phase2_keys(event_type: str, keys: list[str]) -> list[str]:
    """An event's payload keys without the ones ADR 0031 §3 adds."""
    return list(without_reconstruction_keys(event_type, dict.fromkeys(keys)))


def phase2_projection(baseline: dict[str, Any]) -> dict[str, Any]:
    """``baseline`` (current runs) projected onto the Phase 2 golden's keys (plan D7): each
    event's §3 keys dropped, and an ``accept_input`` transition shown as Phase 2 recorded it
    (its event had no ``to``). Nothing else changes."""
    projected = {}
    for name, run in baseline.items():
        transitions, index = list(run["run_transitions"]), 0
        for event_type, keys in zip(run["event_types"], run["payload_keys"], strict=True):
            if event_type == RunEventType.RUN_STATE_CHANGED:
                if "state" in keys:
                    transitions[index] = "None"
                index += 1
        projected[name] = {
            **run,
            "payload_keys": [
                phase2_keys(t, k)
                for t, k in zip(run["event_types"], run["payload_keys"], strict=True)
            ],
            "run_transitions": transitions,
        }
    return projected


def main() -> None:
    baseline = asyncio.run(record_baseline())
    GOLDEN_V3.parent.mkdir(exist_ok=True)
    GOLDEN_V3.write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(f"wrote {GOLDEN_V3} ({len(baseline)} runs)")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    main()
