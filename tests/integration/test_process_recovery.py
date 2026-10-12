"""Actual process death with a persistent synthetic provider and isolated PG ledger."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DSN = os.environ.get("E_AGENT_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="no isolated PostgreSQL test ledger")
ROOT = Path(__file__).resolve().parents[2]

WORKER = r"""
import asyncio, json, os, pathlib, runpy, sys
from e_agent.adapters.postgres import apply_migrations, PostgresRunStore
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.run import RunState
root, folder, mode, boundary = sys.argv[1:]
folder = pathlib.Path(folder)
ns = runpy.run_path(str(pathlib.Path(root) / 'packages/kernel/tests/conftest.py'))
async def main():
    dsn = os.environ['E_AGENT_TEST_PG_DSN']
    await apply_migrations(dsn)
    store = await PostgresRunStore.open(dsn)
    k = ns['make_kernel'].__wrapped__(store)()
    if mode == 'writer':
        # ADR 0020: an earlier boundary (intent, dispatch) leaves an unresolved write that makes the
        # connection busy, so every boundary starts from an empty ledger.
        await store.truncate_for_tests()
        run = await k.coordinator.start_run(k.requester, 'synthetic process recovery', k.scope)
        (folder / 'run.json').write_text(json.dumps({'run_id': run.run_id}))
        if boundary == 'waiting':
            (folder / 'provider.json').write_text(json.dumps({
                'notes': k.backend.notes, 'create_calls': k.backend.create_calls}))
            os._exit(91)
        execute = k.backend.execute
        async def external(*args):
            if boundary == 'intent':
                (folder / 'provider.json').write_text(json.dumps({
                    'notes': k.backend.notes, 'create_calls': k.backend.create_calls}))
                os._exit(91)
            receipt = await execute(*args)
            (folder / 'provider.json').write_text(json.dumps({
                'notes': k.backend.notes, 'create_calls': k.backend.create_calls}))
            if boundary == 'dispatch':
                os._exit(91)
            return receipt
        k.backend.execute = external
        methods = {'approval': 'record_approval', 'reservation': 'reserve_operation',
                   'receipt': 'record_receipt', 'outcome': 'record_outcome'}
        if boundary in methods:
            method = methods[boundary]
            original = getattr(store, method)
            async def persist_then_die(*args, **kwargs):
                await original(*args, **kwargs)
                (folder / 'provider.json').write_text(json.dumps({
                    'notes': k.backend.notes, 'create_calls': k.backend.create_calls}))
                os._exit(91)
            setattr(store, method, persist_then_die)
        if boundary == 'terminal':
            update = store.update_run
            async def terminal_then_die(*args, **kwargs):
                result = await update(*args, **kwargs)
                if args[0].state == RunState.SUCCEEDED:
                    os._exit(91)
                return result
            store.update_run = terminal_then_die
        p = await k.coordinator.pending_approval(ns['TENANT'], run.run_id)
        await k.coordinator.decide(actor=k.approver, run_id=run.run_id,
            action_id=p.action_id, action_digest=p.digest,
            expected_run_revision=p.run_revision, decision=ApprovalDecision.APPROVED)
        raise AssertionError('crash boundary not reached')
    provider = json.loads((folder / 'provider.json').read_text())
    k.backend.notes = provider['notes']
    k.backend.create_calls = provider['create_calls']
    run_id = json.loads((folder / 'run.json').read_text())['run_id']
    before = await store.get_run(ns['TENANT'], run_id)
    run = await k.coordinator.recover_run(ns['TENANT'], run_id)
    recovered_state = run.state
    if run.state == RunState.NEEDS_RECONCILIATION:
        run = await k.coordinator.reconcile(k.approver, run_id)
    expected_effects = 0 if boundary in {'waiting', 'approval', 'reservation', 'intent'} else 1
    expected_state = {
        'waiting': RunState.WAITING_APPROVAL, 'intent': RunState.NEEDS_RECONCILIATION,
        'approval': RunState.FAILED, 'reservation': RunState.FAILED,
    }.get(boundary, RunState.SUCCEEDED)
    assert run.state == expected_state, run
    assert k.backend.create_calls == expected_effects
    result = {'before': str(before.state), 'recovered': str(recovered_state),
              'after': str(run.state), 'create_calls': k.backend.create_calls}
    await store.close()
    print(json.dumps(result))
asyncio.run(main())
"""


@pytest.mark.parametrize(
    "boundary",
    ["waiting", "approval", "reservation", "intent", "dispatch", "receipt", "outcome", "terminal"],
)
def test_process_exit_recovers_without_replaying_effect(tmp_path: Path, boundary: str) -> None:
    args = [sys.executable, "-c", WORKER, str(ROOT), str(tmp_path)]
    died = subprocess.run([*args, "writer", boundary], capture_output=True, text=True, timeout=30)
    assert died.returncode == 91, died.stdout + died.stderr
    recovered = subprocess.run(
        [*args, "reader", boundary], capture_output=True, text=True, timeout=30
    )
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    result = json.loads(recovered.stdout)
    effects = 0 if boundary in {"waiting", "approval", "reservation", "intent"} else 1
    assert result["create_calls"] == effects
    expected = {
        "waiting": "WAITING_APPROVAL",
        "intent": "NEEDS_RECONCILIATION",
        "approval": "FAILED",
        "reservation": "FAILED",
    }.get(boundary, "SUCCEEDED")
    assert result["after"] == expected
    if boundary == "dispatch":
        assert result["recovered"] == "NEEDS_RECONCILIATION"

    evidence_dir = os.environ.get("E_AGENT_TEST_PROCESS_EVIDENCE_DIR")
    if evidence_dir:
        target = Path(evidence_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{boundary}.json").write_text(
            json.dumps(
                {
                    "boundary": boundary,
                    "writer_exit_code": died.returncode,
                    "recovery_exit_code": recovered.returncode,
                    "result": result,
                    "provider": json.loads((tmp_path / "provider.json").read_text()),
                },
                indent=2,
            )
        )
