"""Record the prompts `e-agent demo` sends for every task kind (golden for Task 1d.3).

Runs the CLI's own demo path with the runtime stubbed out and captures the text
passed to ``start_run``. Run on unchanged code:
``uv run python tests/unit/server/record_demo_prompts.py``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from e_agent.server import cli
from e_agent.server.profile import Profile, load_profile

GOLDEN = Path(__file__).parent / "golden" / "demo_prompts.json"
TASKS = (
    "draft-po",
    "shortage",
    "recommend",
    "amend-rfq",
    "quotation",
    "late-orders",
    "crm-lead",
    "overdue-invoices",
)
REF_KEYS = (
    "rfq_ref",
    "customer_ref",
    "product_ref",
    "contact_ref",
    "team_ref",
    "owner_ref",
    "other_owner_ref",
    "source_ref",
    "as_of",
)


class _Captured(Exception):
    def __init__(self, prompt: str) -> None:
        self.prompt = prompt


async def _start_run(_operator: Any, prompt: str, _scope: Any) -> None:
    raise _Captured(prompt)


async def _build_runtime(_profile: Profile, **_kw: Any) -> Any:
    coordinator = SimpleNamespace(start_run=_start_run)
    return SimpleNamespace(coordinator=coordinator, operator=None, scope=None)


def _profiles() -> dict[str, Profile]:
    base = load_profile()
    refs = {key: f"{key}:LIVE" for key in REF_KEYS}
    legacy = {"demand_ref": "demand:LEGACY", "product_ref": "product:LEGACY"}
    return {
        "default": base,
        "refs": base.model_copy(update={"driver": base.driver.model_copy(update={"refs": refs})}),
        "legacy": base.model_copy(update={"driver": base.driver.model_copy(update=legacy)}),
        "legacy+refs": base.model_copy(
            update={"driver": base.driver.model_copy(update={**legacy, "refs": refs})}
        ),
    }


def _capture(profile: Profile, argv: list[str]) -> str:
    args = cli.build_parser().parse_args(["demo", *argv])
    with (
        mock.patch.object(cli, "load_profile", return_value=profile),
        mock.patch.object(cli, "build_runtime", _build_runtime),
    ):
        try:
            asyncio.run(cli._demo(args))
        except _Captured as captured:
            return captured.prompt
    raise AssertionError("demo did not start a run")


def capture_prompts() -> dict[str, str]:
    prompts: dict[str, str] = {}
    for name, profile in _profiles().items():
        prompts[f"{name}/<profile task>"] = _capture(profile, [])
        for task in TASKS:
            prompts[f"{name}/{task}"] = _capture(profile, ["--task", task])
    return prompts


if __name__ == "__main__":
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(capture_prompts(), indent=2, sort_keys=True) + "\n", "utf-8")
    print(f"wrote {GOLDEN}")
