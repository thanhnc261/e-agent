"""`features.execution_ir: on`, single-step plans (Task 2c.6, ADR 0025, ADR 0027, ADR 0028).

The run resolves its task definition at admission; its tool set is the definition's
capabilities, passed to the driver on every turn and enforced by the kernel. A write proposal
compiles to a 1-step plan, validated and approved with today's digest and presentation, and
each stage writes step records in the same batch as its events. Acceptance is checked at run
end. Before the first reservation an IR failure falls back to today's path. Runs over both
stores through the `run_store` fixture (ENG-STORE-1); no plugin is imported.
"""

from datetime import UTC, datetime

from e_agent.contracts.outcome import OutcomeCheck, OutcomeReport, OutcomeStatus
from e_agent.contracts.run import ReasonCode
from e_agent.contracts.task import (
    AcceptanceSpec,
    AnswerCondition,
    RequiredEffect,
    acceptance_met,
)
from e_agent.kernel.evidence import classify

WRITE = "notes.note.create.v1"
ANSWER = "notes.summary.answer.v1"
T0 = datetime(2026, 10, 6, tzinfo=UTC)


def _report(status: OutcomeStatus, *checks: tuple[str, bool, str]) -> OutcomeReport:
    return OutcomeReport(
        run_id="run_1",
        action_id="act_1",
        status=status,
        checks=tuple(
            OutcomeCheck(name=n, passed=p, expected=e, observed="model") for n, p, e in checks
        ),
        verifier_id="v",
        verifier_version="1",
        reported_at=T0,
    )


# -- acceptance (pure) -------------------------------------------------------------------
def test_acceptance_unmet_is_classified_failed() -> None:
    assert classify("FAILED", "acceptance unmet", "fixture", ReasonCode.ACCEPTANCE_UNMET) == (
        "fixture:failed"
    )


def test_acceptance_met_is_disjunctive() -> None:
    both = AcceptanceSpec(
        required_effects=(RequiredEffect(contract_id=WRITE, min_verified=2),),
        required_answer=ANSWER,
        answer_condition=AnswerCondition(check="count", expected="0"),
    )
    zero = _report(OutcomeStatus.VERIFIED, ("count", True, "0"))
    positive = _report(OutcomeStatus.VERIFIED, ("count", True, "3"))
    unverified = _report(OutcomeStatus.FAILED, ("count", True, "0"))
    cases = [
        (both, {WRITE: 2}, [], True),  # the effects alternative
        (both, {WRITE: 1}, [], False),  # below min_verified
        (both, {WRITE: 1}, [zero], True),  # the answer alternative, condition met
        (both, {}, [positive], False),  # an accurate positive answer is not the no-op
        (both, {}, [unverified], False),  # an unverified report never counts
        (AcceptanceSpec(required_answer=ANSWER), {}, [positive], True),  # no condition
        (AcceptanceSpec(required_answer=ANSWER), {WRITE: 5}, [], False),  # only the answer
        (AcceptanceSpec(required_effects=(RequiredEffect(contract_id=WRITE),)), {}, [zero], False),
        (AcceptanceSpec(), {}, [], True),  # nothing required
    ]
    for spec, verified, answers, expected in cases:
        assert acceptance_met(spec, verified, answers) is expected, (spec, verified, answers)
    print(f"acceptance cases: {len(cases)}")
    assert len(cases) == 9
