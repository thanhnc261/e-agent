"""Run a gate set and record evidence tied to the commit (harness plan H2, gate)."""

from __future__ import annotations

import contextlib
import os
import re
import signal
import subprocess
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from e_agent_harness import contracts, gitinfo
from e_agent_harness.manifest import Manifest, path_matches
from e_agent_harness.state import BOOKKEEPING, write_json

TAIL_LINES = 40
TIMEOUT_EXIT = 124
COUNT_RE = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|warnings?)\b")
_KEY = r"(?:password|passwd|secret|token|api[_-]?key|authorization|dsn)"
# key=value, key: value, "key": "value", --key=value (quotes optional on both sides)
SECRET_RE = re.compile(rf"(?i)([\"']?(?:--)?{_KEY}[\"']?\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)")
# --key value (CLI flag with a separate argument)
FLAG_RE = re.compile(rf"(?i)(--{_KEY}\s+)(\S+)")
# Bearer <token>
BEARER_RE = re.compile(r"(?i)(\bbearer\s+)(\S+)")
URL_PASSWORD_RE = re.compile(r"(://[^:/\s@]+:)[^@\s]+@")

Runner = Callable[[str, Path, int], tuple[int, str]]


def redact(text: str) -> str:
    text = URL_PASSWORD_RE.sub(r"\1[REDACTED]@", text)
    text = BEARER_RE.sub(r"\1[REDACTED]", text)
    text = FLAG_RE.sub(r"\1[REDACTED]", text)
    return SECRET_RE.sub(r"\1[REDACTED]", text)


def parse_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for number, label in COUNT_RE.findall(text):
        key = {"error": "errors", "warning": "warnings"}.get(label, label)
        counts[key] = int(number)
    return counts


def _tail(text: str) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-TAIL_LINES:])


def _text(data: str | bytes | None) -> str:
    if data is None:
        return ""
    return data.decode(errors="replace") if isinstance(data, bytes) else data


def run_shell(command: str, cwd: Path, timeout: int) -> tuple[int, str]:
    # Gate commands come from the committed manifest, not from model output.
    # The command runs in its own session so a timeout kills the whole process group,
    # not only the shell (pytest under ``uv run`` would otherwise keep running).
    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        output, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        output, _ = proc.communicate()
        return TIMEOUT_EXIT, f"{_text(output)}\n[timeout after {timeout}s]"
    return proc.returncode, _text(output)


def code_is_clean(repo_root: Path) -> bool:
    """No change outside harness bookkeeping: earlier uncommitted evidence does not count."""
    return not [
        p
        for p in gitinfo.status_files(repo_root)
        if not any(path_matches(p, pattern) for pattern in BOOKKEEPING)
    ]


def database_identity(dsn: str) -> tuple[str, int, str]:
    """(host, port, database) of a PostgreSQL DSN in URL or keyword form."""
    dsn = dsn.strip()
    if "://" in dsn:
        parts = urlsplit(dsn)
        return (parts.hostname or "localhost", parts.port or 5432, parts.path.lstrip("/"))
    fields = dict(item.split("=", 1) for item in dsn.split() if "=" in item)
    return (
        fields.get("host") or "localhost",
        int(fields.get("port") or 5432),
        fields.get("dbname") or fields.get("database") or "",
    )


def check_guards(m: Manifest, set_name: str, env: Mapping[str, str]) -> list[str]:
    """Problems that forbid running the gate set; never echoes a DSN (it may hold a secret)."""
    guard = m.gate_guards.get(set_name)
    if guard is None:
        return []
    problems = [f"{name} is not set" for name in guard.require_env if not env.get(name)]
    for left, right in guard.distinct_databases:
        both = env.get(left) and env.get(right)
        if both and database_identity(env[left]) == database_identity(env[right]):
            problems.append(f"{left} and {right} name the same database")
    return problems


def run_gate(
    m: Manifest,
    set_name: str,
    repo_root: Path,
    *,
    task_id: str,
    package: str | None = None,
    timeout: int = 1800,
    keep_going: bool = False,
    now: datetime,
    runner: Runner = run_shell,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if set_name not in m.gates:
        raise ValueError(f"unknown gate set: {set_name} (have {', '.join(sorted(m.gates))})")
    refused = check_guards(m, set_name, os.environ if env is None else env)
    if refused:
        raise ValueError(f"gate {set_name} refused: " + "; ".join(refused))
    evidence: dict[str, Any] = {
        "gate_set": set_name,
        "task": task_id,
        "commit": gitinfo.head_sha(repo_root),
        "clean_tree": code_is_clean(repo_root),
        "started_at": now.isoformat(timespec="seconds"),
        "ok": True,
        "commands": [],
    }
    for template in m.gates[set_name]:
        command = template.replace("{package}", package or ".")
        started = time.monotonic()
        code, output = runner(command, repo_root, timeout)
        evidence["commands"].append(
            {
                "command": redact(command),
                "exit_code": code,
                "seconds": round(time.monotonic() - started, 3),
                "output_tail": redact(_tail(output)),
                "counts": parse_counts(output),
            }
        )
        if code != 0:
            evidence["ok"] = False
            if not keep_going:
                break
    problems = contracts.validate("gate-evidence", evidence)
    if problems:
        raise ValueError("evidence invalid: " + "; ".join(problems))
    return evidence


def write_evidence(directory: Path, evidence: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = str(evidence["started_at"]).replace(":", "-")
    base = f"{stamp}-{evidence['gate_set']}"
    path = directory / f"{base}.json"
    n = 2
    while path.exists():  # two runs of one set within a second must not overwrite
        path = directory / f"{base}-{n}.json"
        n += 1
    write_json(path, evidence)
    return path
