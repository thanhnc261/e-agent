"""The release report must not pass on zero cases (PR-31, ENG-EVID-4)."""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "release_report", REPO / "scripts" / "release_report.py"
)
assert _spec is not None
assert _spec.loader is not None
rr = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rr  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(rr)


def test_release_report_fails_on_zero_cases() -> None:
    code, text = rr.summarize([], "out.json")
    assert code == 1
    assert "0/0" in text


def test_release_report_summary_unchanged_for_non_empty_runs() -> None:
    results = [
        {"passed": True, "task": "ERP-01", "case": "a", "final_state": "SUCCEEDED"},
        {"passed": False, "task": "ERP-02", "case": "b", "final_state": "FAILED"},
    ]
    code, text = rr.summarize(results, "out.json")
    assert code == 1
    assert text == (
        "ok  ERP-01 a: SUCCEEDED\nFAIL ERP-02 b: FAILED\n1/2 cases passed -> out.json\n"
    )
    code, text = rr.summarize(results[:1], "out.json")
    assert code == 0
    assert text.endswith("1/1 cases passed -> out.json\n")
