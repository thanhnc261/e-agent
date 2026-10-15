"""Task presets come from the domain pack; task_kind is a string checked at startup (R-3).

The server holds no table of task kinds or demo prompts: the CLI renders the
prompt from the admitted preset, and bootstrap refuses a kind no admitted
plugin contributes.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Iterator
from typing import Any

import pytest
from e_agent.erp.plugin import TASK_PRESETS
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.server import cli
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import DriverConfig, Profile, load_profile
from pydantic import ValidationError

from .record_demo_prompts import GOLDEN, TASKS, capture_prompts


def _profile(**driver: Any) -> Profile:
    data = load_profile().model_dump(mode="json")
    data["driver"] |= driver
    return Profile.model_validate(data)


def test_cli_demo_prompts_unchanged() -> None:
    assert capture_prompts() == json.loads(GOLDEN.read_text("utf-8"))


async def test_unknown_task_kind_refused_at_startup() -> None:
    with pytest.raises(KernelError) as exc:
        await build_runtime(_profile(task_kind="no-such-task"))
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    assert "no-such-task" in exc.value.safe_message
    with pytest.raises(KernelError) as exc:
        await build_runtime(load_profile(), task_kind="no-such-task")
    assert exc.value.code is ErrorCode.STARTUP_REJECTED


def test_profile_accepts_non_erp_task_kind_string() -> None:
    assert _profile(task_kind="notes-summary").driver.task_kind == "notes-summary"
    assert load_profile().driver.task_kind == "draft-po"


async def test_task_kind_choices_come_from_presets() -> None:
    contributed = {preset.kind for preset in TASK_PRESETS}
    assert contributed == set(TASKS)
    rt = await build_runtime(load_profile())
    assert set(rt.registry.task_presets) == contributed
    # The parser holds no list of kinds; the admitted presets decide at startup.
    args = cli.build_parser().parse_args(["demo", "--task", "notes-summary"])
    assert args.task == "notes-summary"
    with pytest.raises(KernelError) as exc:
        await build_runtime(load_profile(), task_kind="notes-summary")
    assert all(kind in exc.value.safe_message for kind in contributed)


# The demo prompt rendering at 59dbb9c, copied verbatim with its constants frozen,
# then changed on purpose in Task 1d.4: the old top-level keys fold into refs, and
# every ref, demand_ref included, applies in the preset's order.
BASELINE_PROMPTS = {
    "draft-po": "Restock product:widget-a for demand:d-001 by creating a draft purchase order.",
    "shortage": "Calculate the shortage of product:widget-a for demand:d-001.",
    "recommend": "Recommend an approved offer for product:widget-a and demand:d-001 within budget.",
    "amend-rfq": (
        "Amend draft RFQ rfq:po-100 to quantity 15, retaining its current requested date."
    ),
    "quotation": "Create a draft quotation for customer:acme for product:widget-a, quantity 2.",
    "late-orders": "Report late sales orders as of 2026-10-06.",
    "crm-lead": (
        "Create a CRM lead for contact:jane assigned to user:alice in team:direct "
        "from source:website."
    ),
    "overdue-invoices": "Report overdue customer invoices as of 2026-10-06.",
}
BASELINE_REFS = {
    "rfq_ref": "rfq:po-100",
    "customer_ref": "customer:acme",
    "product_ref": "product:widget-a",
    "contact_ref": "contact:jane",
    "team_ref": "team:direct",
    "owner_ref": "user:alice",
    "other_owner_ref": "user:carol",
    "source_ref": "source:website",
    "as_of": "2026-10-06",
    "demand_ref": "demand:d-001",
}


def _baseline_prompt(task: str, driver: DriverConfig) -> str:
    prompt = BASELINE_PROMPTS[task]
    for key, old in BASELINE_REFS.items():
        if key in driver.refs:
            prompt = prompt.replace(old, driver.refs[key])
    return prompt


def _override_cases() -> Iterator[dict[str, Any]]:
    """Every pair of overrides drawn from values that collide with other defaults."""
    slots = [("demand_ref",), ("product_ref",)] + [("refs", key) for key in BASELINE_REFS]
    pool = ("product:widget-a", "customer:acme", "demand:d-001", "rfq:po-100", "user:carol", "X")
    yield {}
    for a, b in itertools.combinations(slots, 2):
        for va, vb in itertools.product(pool, repeat=2):
            fields: dict[str, Any] = {"refs": {}}
            for slot, value in ((a, va), (b, vb)):
                if slot[0] == "refs":
                    fields["refs"][slot[1]] = value
                else:
                    fields[slot[0]] = value
            yield fields


def test_demo_prompt_matches_baseline_for_colliding_overrides() -> None:
    presets = {preset.kind: preset for preset in TASK_PRESETS}
    assert set(presets) == set(BASELINE_PROMPTS)
    cases = refused = 0
    for fields in _override_cases():
        old = {k: v for k, v in fields.items() if k != "refs"}
        if any(fields.get("refs", {}).get(k, v) != v for k, v in old.items()):
            # An old key that differs from its refs entry is refused, never resolved.
            with pytest.raises(ValidationError):
                DriverConfig.model_validate(fields)
            refused += 1
            continue
        driver = DriverConfig.model_validate(fields)
        for task, preset in presets.items():
            assert cli.demo_prompt(preset, driver) == _baseline_prompt(task, driver), (task, fields)
            cases += 1
    assert refused > 0
    assert cases > 10_000
