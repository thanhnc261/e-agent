"""Every model call goes through `_with_tools` (ADR 0032 §9, T23).

`_with_tools` (``kernel/ir_on.py``) is the one place the per-call route check runs, so a
``_driver.advance`` call whose driver input is not built by it would reach the model without
the check. This scans the kernel for every reference to ``<x>._driver.advance`` and requires
the call that uses it, direct or through ``functools.partial``, to pass a ``_with_tools(...)``
call as the driver input.
"""

from __future__ import annotations

import ast
from pathlib import Path

KERNEL = Path(__file__).resolve().parents[2] / "src/e_agent/kernel"


def _is_advance(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "advance"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "_driver"
    )


def _is_with_tools(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_with_tools"
    )


def _sites(tree: ast.AST) -> tuple[list[int], list[int]]:
    """(lines of advance references with a `_with_tools` input, lines of those without)."""
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    good: list[int] = []
    bad: list[int] = []
    for node in ast.walk(tree):
        if not _is_advance(node):
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Call) and parent.func is node:  # self._driver.advance(ctx, x)
            inputs = parent.args[1:]
        elif isinstance(parent, ast.Call) and parent.args[:1] == [node]:  # partial(advance, ...)
            inputs = parent.args[2:]
        else:  # stored, passed on or called in any other way: not checkable, so refused
            inputs = []
        (good if len(inputs) == 1 and _is_with_tools(inputs[0]) else bad).append(node.lineno)
    return good, bad


def test_every_driver_call_goes_through_with_tools() -> None:
    checked = 0
    bypasses: list[str] = []
    for path in sorted(KERNEL.glob("*.py")):
        good, bad = _sites(ast.parse(path.read_text("utf-8")))
        checked += len(good) + len(bad)
        bypasses += [f"{path.name}:{line}" for line in bad]
    print(f"driver call sites checked: {checked}")
    assert checked, "no _driver.advance call site found; the scan is broken"
    assert not bypasses, f"_driver.advance without _with_tools: {bypasses}"
    assert checked == 2, "a new model call site: check it passes the route check (ADR 0032 §9)"


def test_the_scan_refuses_a_bypass() -> None:
    bypass = ast.parse(
        "async def f(self, ctx, x):\n"
        "    await self._driver.advance(ctx, x)\n"
        "    g = self._driver.advance\n"
        "    partial(self._driver.advance, ctx, self._with_tools(r, c, x))\n"
    )
    good, bad = _sites(bypass)
    assert (len(good), len(bad)) == (1, 2)
