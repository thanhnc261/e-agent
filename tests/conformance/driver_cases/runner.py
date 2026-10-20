"""Run the cases against one adapter, checking every not-applicable declaration first.

A declaration is accepted only when its reason is a `NotApplicable` member, the case names
that reason in ``needs``, and the claim holds structurally for the adapter's subject
(`check_claim`). Anything else is a failure of the suite for that driver, never a skip.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .cases import CASES, Case
from .harness import REASON_TEXT, DriverAdapter, NoContinuation, NoModel, NotApplicable
from .world import DRAFT_PO_TASK, VERIFIED, Host, World, advance, ctx, erp_world, to_proposal


@dataclass
class SuiteResult:
    passed: list[str] = field(default_factory=list)
    not_applicable: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


async def check_claim(adapter: DriverAdapter, reason: NotApplicable) -> None:
    """Fail unless ``reason`` holds for a subject of ``adapter`` after a full draft-po run."""
    subject = adapter.subject("draft-po")
    run = ctx(f"run-claim-{reason.value}")
    host = Host(DRAFT_PO_TASK)
    await to_proposal(subject.driver, run, host)
    await advance(subject.driver, run, host, action_result=VERIFIED)
    driver = subject.driver
    if reason in (NotApplicable.NO_MODEL, NotApplicable.NO_TOKEN_SPEND):
        try:
            views = subject.views()
        except NoModel:
            pass
        else:
            raise AssertionError(f"claims {reason.value}, but it has a model ({len(views)} views)")
    if reason is NotApplicable.NO_TOKEN_SPEND:
        tokens_used = getattr(driver, "tokens_used", None)
        spent = 0 if tokens_used is None else tokens_used(run.run_id)
        assert spent == 0, f"claims {reason.value}, but it reports {spent} tokens"
    if reason is NotApplicable.NO_CONTINUATION:
        found = [name for name in ("snapshot", "restore") if hasattr(driver, name)]
        assert not found, f"claims {reason.value}, but it has {found}"
        try:
            subject.snapshot(run.run_id)
        except NoContinuation:
            return
        raise AssertionError(f"claims {reason.value}, but its subject returns a snapshot")


async def run_conformance(
    adapter: DriverAdapter, cases: Sequence[Case] = CASES, w: World | None = None
) -> SuiteResult:
    """Every case against ``adapter``: passed, declared not applicable (and checked), or
    failed with its reason. Refuses an empty case list (PR-31)."""
    assert cases, "the driver conformance suite has no cases"
    w = w or await erp_world()
    result = SuiteResult()
    by_id = {c.case_id: c for c in cases}
    unknown = sorted(set(adapter.not_applicable) - set(by_id))
    result.failed.extend(
        f"{case_id}: declared not applicable but no such case" for case_id in unknown
    )
    claims: dict[NotApplicable, str | None] = {}
    for case in cases:
        declared = adapter.not_applicable.get(case.case_id)
        if declared is not None:
            if not isinstance(declared, NotApplicable):
                result.failed.append(f"{case.case_id}: unknown not-applicable reason {declared!r}")
                continue
            if declared not in case.needs:
                result.failed.append(
                    f"{case.case_id}: {declared.value} is not a reason this case accepts "
                    f"({sorted(n.value for n in case.needs)})"
                )
                continue
            if declared not in claims:
                try:
                    await check_claim(adapter, declared)
                except Exception as exc:
                    claims[declared] = f"{type(exc).__name__}: {exc}"
                else:
                    claims[declared] = None
            if (broken := claims[declared]) is not None:
                result.failed.append(f"{case.case_id}: false {declared.value} claim: {broken}")
                continue
            result.not_applicable.append(
                f"{case.case_id}: {declared.value} ({REASON_TEXT[declared]})"
            )
            continue
        try:
            await case.run(adapter, w)
        except Exception as exc:  # every failure is reported, not only the first
            result.failed.append(f"{case.case_id}: {type(exc).__name__}: {exc}")
        else:
            result.passed.append(case.case_id)
    return result
