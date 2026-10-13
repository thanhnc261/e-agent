"""Evidence classification reads typed reason codes first (ADR 0018)."""

from collections.abc import Callable
from typing import Any

import pytest
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEvent
from e_agent.contracts.run import ReasonCode
from e_agent.kernel import evidence
from e_agent.kernel.evidence import build_evidence, classify

from .conftest import TENANT, Kernel


def test_reason_code_decides_the_class_before_any_text() -> None:
    assert classify("FAILED", "whatever", "fixture", ReasonCode.POLICY_DENIED) == (
        "fixture:blocked-by-design"
    )
    assert classify("FAILED", "whatever", "fixture", ReasonCode.BUDGET_EXHAUSTED) == (
        "fixture:infrastructure-or-budget"
    )
    assert classify("FAILED", "whatever", "fixture", ReasonCode.APPROVAL_EXPIRED) == (
        "fixture:failed"
    )


def test_guard_refusals_are_blocked_but_a_failed_read_back_is_a_failure() -> None:
    assert classify("FAILED", "x", "fixture", ReasonCode.STALE) == "fixture:blocked-by-design"
    # After a COMMITTED receipt the write happened; the read-back disagreed. Not a guard.
    assert classify("FAILED", "x", "fixture", ReasonCode.VERIFICATION_FAILED) == ("fixture:failed")


def test_rows_without_a_code_fall_back_to_the_text_rules() -> None:
    assert classify("FAILED", "validation blocked", "fixture") == "fixture:blocked-by-design"
    assert classify("FAILED", "budget exhausted: turns", "fixture") == (
        "fixture:infrastructure-or-budget"
    )
    assert classify("SUCCEEDED", None, "live") == "live:succeeded"
    assert classify("RUNNING", None, "live") == "live:unresolved"


class _FirstEvents:
    """A store view whose run ledger holds only its first `count` events (paging honoured)."""

    def __init__(self, store: Any, count: int) -> None:
        self._store, self._count = store, count

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)

    async def list_events(
        self, tenant_id: str, run_id: str, after_sequence: int = 0, limit: int | None = None
    ) -> list[RunEvent]:
        events = (await self._store.list_events(tenant_id, run_id))[: self._count]
        events = [e for e in events if e.sequence > after_sequence]
        return events if limit is None else events[:limit]


@pytest.mark.parametrize("count", [4, 5])
async def test_evidence_export_pages_without_losing_or_repeating_events(
    make_kernel: Callable[..., Kernel], monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    await k.coordinator.decide(
        actor=k.approver,
        run_id=run.run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )
    full = await k.store.list_events(TENANT, run.run_id)
    assert len(full) > count
    monkeypatch.setattr(evidence, "EVIDENCE_PAGE", 2)  # an exact multiple (4) and a remainder (5)
    bundle = await build_evidence(
        _FirstEvents(k.store, count),  # type: ignore[arg-type]
        TENANT,
        run.run_id,
        environment="fixture",
        versions={},
    )
    sequences = [e["sequence"] for e in bundle["events"]]
    assert sequences == [e.sequence for e in full[:count]]
    assert len(set(sequences)) == count
