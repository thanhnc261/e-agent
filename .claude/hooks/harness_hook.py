#!/usr/bin/env python3
"""Claude Code hook entry for the e-agent development harness (stdlib only).

Called from .claude/settings.json as
``python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/harness_hook.py <args>``.

The hook payload arrives on stdin. The repository is the nearest ancestor of the
payload's ``cwd`` that holds ``harness/context.toml`` (a worktree is its own
repository), and the harness runs from there:
``uv run --directory <repo> e-agent-harness <args>``, or the current interpreter's
``e_agent_harness`` when the repository is not a uv project.

Failure policy: ``check-scope`` fails closed (exit 2), because an unchecked edit is
worse than a refused one; ``close-check`` fails closed only when
E_AGENT_HARNESS_UNATTENDED=1; ``status`` and ``checkpoint`` never block.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

MANIFEST = Path("harness") / "context.toml"
TIMEOUT = 110


def _fails_closed(command: str) -> bool:
    if command == "check-scope":
        return True
    return command == "close-check" and os.environ.get("E_AGENT_HARNESS_UNATTENDED") == "1"


def _repo_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / MANIFEST).is_file():
            return candidate
    return None


def _runner(root: Path) -> list[str]:
    if (root / "pyproject.toml").is_file():
        return ["uv", "run", "--quiet", "--directory", str(root), "e-agent-harness"]
    return [sys.executable, "-m", "e_agent_harness.cli"]


# --- bash-guard: command shapes that permission rules cannot see -----------------------
#
# Policy, strictest first:
#   deny: the command names a denied container anywhere next to a container tool,
#         whatever the executable path, wrappers, quoting or dynamic form;
#   ask:  the guard cannot see the real command (shell -c, eval, xargs, find -exec,
#         git aliases, another docker daemon or context, a container or compose
#         project outside the allowed list), or it is git push/merge/rebase/reset --hard;
#   none: everything else, left to the permission rules.

_SEPARATORS = re.compile(r"&&|\|\||;|\||&|\n|\$\(|`|\(|\)")
_CONTAINER_TOOL = re.compile(r"(?<![\w-])(?:docker|docker-compose|podman)(?![\w-])")
_DYNAMIC = re.compile(
    r"(?<![\w-])(?:bash|sh|zsh|dash|ksh)\s+-\w*c\b|(?<![\w-])(?:eval|xargs|source)(?![\w-])"
    r"|\s-exec(?:dir)?(?![\w-])"
)
_GIT_WORD = re.compile(r"(?<![\w-])git(?![\w-])")
_CONTAINER_TOOLS = {"docker", "docker-compose", "podman"}
_GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
_DOCKER_OPTIONS_WITH_VALUE = {"--context", "-c", "--host", "-H", "--config", "--log-level", "-l"}
_DOCKER_DAEMON_OPTIONS = {"--context", "-c", "--host", "-H"}
_TARGETING = {
    "exec",
    "stop",
    "start",
    "restart",
    "rm",
    "kill",
    "logs",
    "inspect",
    "cp",
    "attach",
    "pause",
    "unpause",
    "update",
    "rename",
    "top",
    "port",
    "stats",
    "wait",
    "commit",
    "export",
    "diff",
}
_ASK = {"push", "merge", "rebase"}


def _words(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _policy(root: Path) -> tuple[list[str], list[str]]:
    with (root / MANIFEST).open("rb") as fh:
        env = tomllib.load(fh).get("environment", {})
    return (
        [str(p) for p in env.get("denied_containers", [])],
        [str(p) for p in env.get("allowed_containers", [])],
    )


def _git_reason(words: list[str], root: Path) -> str | None:
    i = 1
    while i < len(words) and words[i].startswith("-"):
        if words[i] == "-c" and i + 1 < len(words) and words[i + 1].startswith("alias."):
            return "an inline git alias"
        i += 2 if words[i] in _GIT_OPTIONS_WITH_VALUE else 1
    if i >= len(words):
        return None
    sub, rest = words[i], words[i + 1 :]
    if sub in _ASK or (sub == "reset" and "--hard" in rest):
        return f"git {sub} changes shared history"
    alias = subprocess.run(
        ["git", "-C", str(root), "config", "--get", f"alias.{sub}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if alias:
        expanded = _words(alias)
        if alias.startswith("!") or not expanded:
            return f"git alias {sub} runs a shell command"
        if expanded[0] in _ASK or (expanded[0] == "reset" and "--hard" in expanded):
            return f"git alias {sub} runs git {expanded[0]}"
    return None


def _project_allowed(project: str, allowed: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(f"{project}-x", p) or project == p for p in allowed)


def _docker_reason(segment: str, words: list[str], allowed: list[str]) -> str | None:
    if re.search(r"(?<![\w-])DOCKER_(?:HOST|CONTEXT)=", segment):
        return "another docker daemon or context"
    i = 1
    while i < len(words) and words[i].startswith("-"):
        option = words[i].split("=", 1)[0]
        if option in _DOCKER_DAEMON_OPTIONS:
            return "another docker daemon or context"
        i += 2 if words[i] in _DOCKER_OPTIONS_WITH_VALUE else 1
    compose = Path(words[0]).name == "docker-compose" or (i < len(words) and words[i] == "compose")
    if compose:
        project = None
        for j, word in enumerate(words):
            if word in {"-p", "--project-name"} and j + 1 < len(words):
                project = words[j + 1]
            elif word.startswith("--project-name="):
                project = word.split("=", 1)[1]
        if project is None or not _project_allowed(project, allowed):
            return "a compose project outside the allowed list"
        return None
    if i < len(words) and words[i] in _TARGETING:
        targets = [w for w in words[i + 1 :] if not w.startswith("-")]
        if not any(fnmatch.fnmatchcase(t, p) for t in targets for p in allowed):
            return "a container outside the allowed list"
    return None


def bash_guard(root: Path, command: str) -> tuple[int, str]:
    """(exit code, stdout). Exit 2 denies; stdout may carry an "ask" decision."""
    denied, allowed = _policy(root)
    text = command.replace("\\\n", " ")
    if _CONTAINER_TOOL.search(text):
        for token in re.findall(r"[A-Za-z0-9_.-]+", text):
            if any(fnmatch.fnmatchcase(token, pattern) for pattern in denied):
                print(f"bash-guard: {token} is a denied container ({MANIFEST})", file=sys.stderr)
                return 2, ""
    reasons: list[str] = []
    if _DYNAMIC.search(text) and (_GIT_WORD.search(text) or _CONTAINER_TOOL.search(text)):
        reasons.append("the real command runs through a shell, eval, xargs or -exec")
    for segment in _SEPARATORS.split(text):
        words = _words(segment)
        for index, word in enumerate(words):
            name = Path(word).name
            if name == "git":
                reason = _git_reason(words[index:], root)
            elif name in _CONTAINER_TOOLS:
                reason = _docker_reason(segment, words[index:], allowed)
            else:
                continue
            if reason:
                reasons.append(reason)
            break
    if not reasons:
        return 0, ""
    decision = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "bash-guard: " + "; ".join(dict.fromkeys(reasons)),
        }
    }
    return 0, json.dumps(decision)


def main(argv: list[str]) -> int:
    command = argv[0] if argv else ""
    if command == "close-check" and os.environ.get("E_AGENT_HARNESS_UNATTENDED") != "1":
        return 0  # an attended Stop never runs the gate: return before spawning anything
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    cwd = Path(payload.get("cwd") or os.getcwd())
    root = _repo_root(cwd.resolve() if cwd.exists() else cwd)
    if command == "bash-guard":
        # Outside a repository, the policy of the checkout this script belongs to applies.
        anchor = root if root is not None else Path(__file__).resolve().parents[2]
        if not (anchor / MANIFEST).is_file():
            print(f"bash-guard: no policy at {anchor / MANIFEST}", file=sys.stderr)
            return 2
        root = anchor
        try:
            code, out = bash_guard(root, str((payload.get("tool_input") or {}).get("command", "")))
        except Exception as exc:  # a broken guard must not let a denied command through
            print(f"bash-guard error: {exc}", file=sys.stderr)
            return 2
        sys.stdout.write(out)
        return code
    if root is None:
        if _fails_closed(command):
            print(f"harness hook: no repository with {MANIFEST} above {cwd}", file=sys.stderr)
            return 2
        return 0
    try:
        proc = subprocess.run(
            [*_runner(root), *argv],
            input=raw,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        if _fails_closed(command):
            print(f"harness hook: could not run e-agent-harness: {exc}", file=sys.stderr)
            return 2
        return 0
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode not in (0, 2) and _fails_closed(command):
        return 2  # an unexpected failure of a guarding command still blocks
    return proc.returncode if proc.returncode in (0, 2) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
