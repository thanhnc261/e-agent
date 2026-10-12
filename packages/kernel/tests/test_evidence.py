"""Evidence classification reads typed reason codes first (ADR 0018)."""

from e_agent.contracts.run import ReasonCode
from e_agent.kernel.evidence import classify


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


def test_rows_without_a_code_fall_back_to_the_text_rules() -> None:
    assert classify("FAILED", "validation blocked", "fixture") == "fixture:blocked-by-design"
    assert classify("FAILED", "budget exhausted: turns", "fixture") == (
        "fixture:infrastructure-or-budget"
    )
    assert classify("SUCCEEDED", None, "live") == "live:succeeded"
    assert classify("RUNNING", None, "live") == "live:unresolved"
