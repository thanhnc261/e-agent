"""The kernel test suite imports no plugin (MVP design §13, domain neutrality gate).

``tests/unit/kernel`` proves the kernel runs its full lifecycle with only the
notes fixture domain installed, so no file there may import ``e_agent.plugins``:
not at module top, not lazily inside a function, and not through
``importlib.import_module`` or ``__import__`` with a string literal. A test
module outside ``tests/unit/kernel`` is refused too, because it could import a
plugin on the kernel suite's behalf (``tests/unit/server`` does).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
KERNEL_TESTS = REPO / "tests" / "unit" / "kernel"
KERNEL_PACKAGE = "tests.unit.kernel"
PLUGINS = "e_agent.plugins"
IMPORT_CALLS = frozenset({"import_module", "__import__"})


def _banned(module: str) -> bool:
    if module == PLUGINS or module.startswith(PLUGINS + "."):
        return True
    in_tests = module == "tests" or module.startswith("tests.")
    in_kernel = module == KERNEL_PACKAGE or module.startswith(KERNEL_PACKAGE + ".")
    return in_tests and not in_kernel


def _resolve(package: str, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    parts = package.split(".")
    base = parts[: len(parts) - node.level + 1]
    return ".".join([*base, node.module] if node.module else base)


def violations(source: str, package: str = KERNEL_PACKAGE) -> list[str]:
    """Every import of a plugin (or of a test module outside the kernel suite) in ``source``."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = _resolve(package, node)
            modules = [module, *(f"{module}.{alias.name}" for alias in node.names)]
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in IMPORT_CALLS and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    modules = [arg.value]
        found.extend(f"line {node.lineno}: {m}" for m in modules if _banned(m))
    return found


def _package(path: Path) -> str:
    """The package a kernel test file's relative imports resolve against."""
    return ".".join([KERNEL_PACKAGE, *path.parent.relative_to(KERNEL_TESTS).parts])


def _kernel_test_files() -> list[Path]:
    return sorted(KERNEL_TESTS.rglob("*.py"))


def test_kernel_tests_import_no_plugin() -> None:
    files = _kernel_test_files()
    assert files, f"no Python files found under {KERNEL_TESTS}"
    bad = {
        str(path.relative_to(REPO)): hits
        for path in files
        if (hits := violations(path.read_text("utf-8"), _package(path)))
    }
    print(f"kernel test neutrality: checked {len(files)} files")
    assert not bad, f"kernel tests import a plugin ({len(files)} files checked): {bad}"


@pytest.mark.parametrize(
    "source",
    [
        "import e_agent.plugins.erp.simulator",
        "from e_agent.plugins.erp.simulator import fixture_profile_path",
        "from e_agent import plugins",
        "def f():\n    from e_agent.plugins.erp import simulator\n",
        "import importlib\nimportlib.import_module('e_agent.plugins.erp.simulator')",
        "__import__('e_agent.plugins')",
        "from tests.unit.server.record_demo_prompts import GOLDEN",
        "from ..server import test_api",
    ],
)
def test_checker_finds_a_plugin_import(source: str) -> None:
    assert violations(source)


@pytest.mark.parametrize(
    "source",
    [
        "from e_agent.kernel.coordinator import RunCoordinator",
        "from .conftest import CONN",
        "from tests.unit.kernel.conftest import CONN",
        "import importlib\nimportlib.import_module('e_agent.adapters.postgres')",
        "ENTRY = '[e_agent.plugins.v1]'",
    ],
)
def test_checker_allows_kernel_and_notes_imports(source: str) -> None:
    assert not violations(source)
