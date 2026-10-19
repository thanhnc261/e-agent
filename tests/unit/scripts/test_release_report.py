"""The release report lists the defaulted effect declarations (ADR 0029 Operations, 2c.8a R-3)."""

import importlib.util
import sys
from pathlib import Path

from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import load_profile

from ..server.test_api import FIXTURE_DEFAULTED

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "release_report_2c8a", REPO / "scripts" / "release_report.py"
)
assert _spec is not None and _spec.loader is not None
rr = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rr  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(rr)


async def test_release_report_lists_defaulted_declarations() -> None:
    rt = await build_runtime(load_profile(fixture_profile_path()))
    result = {"passed": True, "task": "ERP-01", "case": "a", "final_state": "SUCCEEDED"}
    report = rr.build_report(rt, [result])
    assert report["defaulted_declarations"] == FIXTURE_DEFAULTED
    assert (report["passed"], report["total"], report["cases"]) == (1, 1, [result])
    assert report["versions"] == rt.versions
    print(f"release report lists {len(FIXTURE_DEFAULTED)} defaulted declarations")
