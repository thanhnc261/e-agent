"""Run a gate set and record evidence tied to the commit (harness plan H2, gate)."""

from __future__ import annotations

import contextlib
import os
import re
import signal
import subprocess
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from e_agent_harness import contracts, gitinfo
from e_agent_harness.manifest import Manifest, path_matches
from e_agent_harness.state import BOOKKEEPING, write_json

TAIL_LINES = 40
TIMEOUT_EXIT = 124
COUNT_RE = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|warnings?)\b")
_KEY = r"(?:password|passwd|secret|token|api[_-]?key|authorization|dsn)"
# A quoted value with backslash escapes, or a bare word.
_VALUE = r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|\S+)"
# key=value, key: value, "key": "value", --key=value (quotes optional on both sides)
SECRET_RE = re.compile(rf"(?i)([\"']?(?:--)?{_KEY}[\"']?\s*[=:]\s*){_VALUE}")
# Authorization: a quoted value, or everything to the end of the line (Digest headers
# carry several parameters).
AUTH_RE = re.compile(r"(?i)(authorization[\"']?\s*[=:]\s*)(?:\"(?:\\.|[^\"\\])*\"|[^\r\n]*)")
# --key value (CLI flag with a separate argument)
FLAG_RE = re.compile(rf"(?i)(--{_KEY}\s+){_VALUE}")
# Bearer <token>
BEARER_RE = re.compile(r"(?i)(\bbearer\s+)(\S+)")
URL_PASSWORD_RE = re.compile(r"(://[^:/\s@]+:)[^@\s]+@")

Runner = Callable[[str, Path, int], tuple[int, str]]


def redact(text: str) -> str:
    text = URL_PASSWORD_RE.sub(r"\1[REDACTED]@", text)
    text = AUTH_RE.sub(r"\1[REDACTED]", text)
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


_CONNINFO_RE = re.compile(r"\s*(\w+)\s*=\s*('(?:\\.|[^'\\])*'|\S+)")


def _conninfo(dsn: str) -> dict[str, str] | None:
    """libpq keyword/value form: ``key = value`` pairs, values optionally single-quoted."""
    params: dict[str, str] = {}
    pos = 0
    while pos < len(dsn):
        if not dsn[pos:].strip():
            break
        match = _CONNINFO_RE.match(dsn, pos)
        if match is None:
            return None
        value = match.group(2)
        if value.startswith("'"):
            value = value[1:-1]
        # libpq unescapes backslashes in quoted and unquoted values alike.
        params[match.group(1).lower()] = re.sub(r"\\(.)", r"\1", value)
        pos = match.end()
    return params or None


def database_name(dsn: str) -> str | None:
    """The database a PostgreSQL DSN names, or None when it cannot be told."""
    dsn = dsn.strip()
    if dsn.startswith(("postgresql://", "postgres://")):
        parts = urlsplit(dsn)
        query: dict[str, str] = {}
        for pair in parts.query.split("&"):
            key, _, value = pair.partition("=")
            if key:
                # percent-decoding only: libpq keeps a literal "+".
                query[unquote(key)] = unquote(value)
        if "dbname" in query:
            return query["dbname"] or None  # an empty override: cannot tell
        return unquote(parts.path.lstrip("/")) or None
    params = _conninfo(dsn)
    return (params or {}).get("dbname") or None


def check_guards(m: Manifest, set_name: str, env: Mapping[str, str]) -> list[str]:
    """Problems that forbid running the gate set; never echoes a DSN (it may hold a secret).

    Guards under ``"*"`` apply to every set. Databases are compared by name only, on any
    host: a test database must have its own name (pilot log HP-13).
    """
    guards = [g for g in (m.gate_guards.get("*"), m.gate_guards.get(set_name)) if g]
    problems: list[str] = []
    for guard in guards:
        problems += [f"{name} is not set" for name in guard.require_env if not env.get(name)]
        for left, right in guard.distinct_databases:
            if not (env.get(left) and env.get(right)):
                continue
            names = {key: database_name(env[key]) for key in (left, right)}
            unknown = [key for key, name in names.items() if name is None]
            if unknown:
                problems.append(f"cannot tell which database {' and '.join(unknown)} names")
            elif names[left] == names[right]:
                problems.append(f"{left} and {right} name the same database")
    return list(dict.fromkeys(problems))


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
    clock: Callable[[], datetime] | None = None,
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
        "started_at": now.isoformat(timespec="microseconds"),
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
    # Read when the last command has ended: a closing checkpoint must come after this.
    finished = (clock or (lambda: datetime.now(UTC)))()
    evidence["finished_at"] = max(finished, now).isoformat(timespec="microseconds")
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
