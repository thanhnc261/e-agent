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
# A command passes silently only when bash-guard has fully parsed it into a known, allowed
# form. Strictest first:
#   deny: a denied container is named next to a container tool, after quotes and backslashes
#         are removed, whatever the executable path or dynamic form;
#   ask:  anything bash-guard cannot parse completely: shell -c (any option form), eval,
#         source, xargs, -exec, variables, substitutions or ANSI-C quoting next to git or a
#         container tool; git subcommands that are not built in (aliases), inline aliases,
#         git push, pull, merge, rebase and reset --hard; docker global options (daemon,
#         context, config), unknown docker subcommands or options, and any target that is
#         not an allowed container or compose project;
#   none: everything else, left to the permission rules.

_CONTAINER_TOOL = re.compile(r"(?<![\w-])(?:docker|docker-compose|podman)(?![\w-])")
_GIT_WORD = re.compile(r"(?<![\w-])git(?![\w-])")
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish"}
_CONTAINER_TOOLS = {"docker", "docker-compose", "podman"}
_GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
_GIT_ASK = {"push", "pull", "merge", "rebase"}
_RESET_SAFE = {"--soft", "--mixed", "-q", "--quiet", "--", "-p", "--patch"}
_GIT_BUILTINS = {
    "add",
    "am",
    "annotate",
    "apply",
    "archive",
    "bisect",
    "blame",
    "branch",
    "bundle",
    "cat-file",
    "check-ignore",
    "checkout",
    "cherry",
    "cherry-pick",
    "clean",
    "clone",
    "commit",
    "config",
    "count-objects",
    "describe",
    "diff",
    "diff-index",
    "diff-tree",
    "difftool",
    "fetch",
    "for-each-ref",
    "format-patch",
    "fsck",
    "gc",
    "grep",
    "hash-object",
    "help",
    "init",
    "log",
    "ls-files",
    "ls-remote",
    "ls-tree",
    "maintenance",
    "merge-base",
    "mv",
    "name-rev",
    "notes",
    "range-diff",
    "reflog",
    "remote",
    "restore",
    "rev-list",
    "rev-parse",
    "revert",
    "rm",
    "shortlog",
    "show",
    "show-ref",
    "stash",
    "status",
    "submodule",
    "switch",
    "symbolic-ref",
    "tag",
    "version",
    "worktree",
}
_DOCKER_READ_ONLY = {"ps", "ls", "list", "images", "version", "info"}
# subcommand: (flags, options taking a value, "all" operands are containers | "first" only)
_DOCKER_TARGETS: dict[str, tuple[set[str], set[str], str]] = {
    "exec": (
        {"-i", "-t", "-it", "-ti", "-d", "--interactive", "--tty", "--detach"},
        set(),
        "first",
    ),
    "logs": (
        {"-f", "--follow", "-t", "--timestamps", "--details"},
        {"--tail", "-n", "--since", "--until"},
        "all",
    ),
    "stop": (set(), {"-t", "--time", "-s", "--signal"}, "all"),
    "restart": (set(), {"-t", "--time", "-s", "--signal"}, "all"),
    "start": ({"-a", "--attach", "-i", "--interactive"}, set(), "all"),
    "kill": (set(), {"-s", "--signal"}, "all"),
    "rm": ({"-f", "--force", "-v", "--volumes"}, set(), "all"),
    "inspect": ({"-s", "--size"}, {"-f", "--format", "--type"}, "all"),
    "top": (set(), set(), "first"),
    "pause": (set(), set(), "all"),
    "unpause": (set(), set(), "all"),
    "wait": (set(), set(), "all"),
    "port": (set(), set(), "first"),
}


_WRAPPERS = {"sudo", "env", "command", "exec", "nohup", "time", "nice", "builtin"}
_ENDPOINT_VARIABLES = ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG")


def _scan(text: str) -> tuple[list[str], bool]:
    """Split a command into simple commands the way the shell does, outside quotes.

    Returns the segments and whether any expansion ($, backticks) appears outside single
    quotes. Command substitutions start a new segment, also inside double quotes.
    """
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    expansion = False
    i = 0

    def cut() -> None:
        segments.append("".join(current))
        current.clear()

    while i < len(text):
        c = text[i]
        if quote == "'":
            current.append(c)
            quote = None if c == "'" else quote
            i += 1
            continue
        if c == "\\" and i + 1 < len(text):
            current.append(text[i : i + 2])
            i += 2
            continue
        if c == "`" or text.startswith("$(", i):
            expansion = True
            cut()
            i += 1 if c == "`" else 2
            continue
        if c == "$":
            expansion = True
        if quote == '"':
            current.append(c)
            quote = None if c == '"' else quote
            i += 1
            continue
        if c in "'\"":
            quote = c
        elif c in ";&|\n()":
            cut()
            i += 1
            continue
        current.append(c)
        i += 1
    cut()
    return [seg for seg in segments if seg.strip()], expansion


def _command_word(words: list[str]) -> str | None:
    """The word in command position, after assignments, wrappers and their options."""
    i = 0
    while i < len(words):
        word = words[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", word):
            i += 1
        elif Path(word).name in _WRAPPERS:
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 2 if words[i] in {"-u", "-g", "-n", "-C"} else 1
        else:
            return word
    return None


def _policy(root: Path) -> tuple[list[str], list[str]]:
    with (root / MANIFEST).open("rb") as fh:
        env = tomllib.load(fh).get("environment", {})
    return (
        [str(p) for p in env.get("denied_containers", [])],
        [str(p) for p in env.get("allowed_containers", [])],
    )


def _dynamic(segments: list[str]) -> bool:
    for segment in segments:
        words = segment.split()
        for i, word in enumerate(words):
            name = Path(word.strip("\"'")).name
            if name in {"eval", "source", "xargs"} or word in {"-exec", "-execdir"}:
                return True
            if i == 0 and word == ".":
                return True
            if name in _SHELLS and any(
                re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", w) or w == "--command" for w in words[i + 1 :]
            ):
                return True
    return False


def _allowed(name: str, allowed: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, p) for p in allowed)


def _git_reason(words: list[str]) -> str | None:
    i = 1
    while i < len(words) and words[i].startswith("-"):
        key = words[i + 1].split("=", 1)[0].lower() if i + 1 < len(words) else ""
        if words[i] == "-c" and key.startswith("alias."):
            return "an inline git alias"
        i += 2 if words[i] in _GIT_OPTIONS_WITH_VALUE else 1
    if i >= len(words):
        return None
    sub, rest = words[i], words[i + 1 :]
    if sub in _GIT_ASK:
        return f"git {sub} changes shared history"
    if sub == "reset" and any(w.startswith("-") and w not in _RESET_SAFE for w in rest):
        return "git reset with an option that can discard work"
    if (sub, tuple(rest[:1])) in {("submodule", ("foreach",)), ("bisect", ("run",))}:
        return f"git {sub} {rest[0]} runs arbitrary commands"
    if sub not in _GIT_BUILTINS and sub != "reset":
        return f"git {sub} is not a built-in bash-guard knows (an alias?)"
    return None


_COMPOSE_SUBCOMMANDS = {
    "ps",
    "logs",
    "top",
    "images",
    "ls",
    "version",
    "config",
    "stop",
    "start",
    "restart",
    "pause",
    "unpause",
}


def _compose_reason(rest: list[str], allowed: list[str]) -> str | None:
    project = None
    j = 0
    while j < len(rest) and rest[j].startswith("-"):
        word = rest[j]
        name = word.split("=", 1)[0]
        if name not in {"-p", "--project-name"}:
            return f"docker compose option {word} (another file or setting) needs the owner"
        project = (
            word.split("=", 1)[1] if "=" in word else (rest[j + 1] if j + 1 < len(rest) else None)
        )
        j += 1 if "=" in word else 2
    if project is None:
        return "docker compose without an allowed project (-p)"
    if not any(fnmatch.fnmatchcase(f"{project}-x", p) or project == p for p in allowed):
        return f"compose project {project} is outside the allowed list"
    sub = rest[j] if j < len(rest) else ""
    if sub not in _COMPOSE_SUBCOMMANDS:
        return f"docker compose {sub or '(no subcommand)'} can create or remove containers"
    return None


def _docker_reason(segment: str, words: list[str], allowed: list[str]) -> str | None:
    if re.search(r"(?<![\w-])DOCKER_[A-Z_]+=", segment):
        return "a docker environment override (daemon, context or config)"
    if Path(words[0]).name == "docker-compose":
        return _compose_reason(words[1:], allowed)
    if len(words) < 2:
        return None
    if words[1].startswith("-"):
        return "docker global options (daemon, context or config)"
    sub, rest = words[1], words[2:]
    if sub == "compose":
        return _compose_reason(rest, allowed)
    if sub == "container":
        if not rest:
            return None
        sub, rest = rest[0], rest[1:]
    if sub in _DOCKER_READ_ONLY:
        return None
    if sub not in _DOCKER_TARGETS:
        return f"docker {sub} is outside the commands bash-guard can check"
    flags, with_value, mode = _DOCKER_TARGETS[sub]
    targets: list[str] = []
    j = 0
    while j < len(rest):
        word = rest[j]
        if mode == "first" and targets:
            break
        if word.startswith("-") and word != "-":
            name = word.split("=", 1)[0]
            if word in flags:
                j += 1
                continue
            if name in with_value:
                j += 1 if "=" in word else 2
                continue
            return f"docker {sub} option {word} is not one bash-guard can check"
        targets.append(word)
        j += 1
    if not targets:
        return f"docker {sub} without a container"
    inner = rest[j:]
    runs_tools = any(Path(w).name in _CONTAINER_TOOLS | {"git"} for w in inner)
    runs_script = any(Path(w).name in _SHELLS for w in inner) and any(
        re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", w) or w == "--command" for w in inner
    )
    if mode == "first" and (runs_tools or runs_script):
        return f"docker {sub} runs a command inside the container that bash-guard cannot check"
    for target in targets:
        if not _allowed(target, allowed):
            return f"{target} is not an allowed container"
    return None


def bash_guard(root: Path, command: str) -> tuple[int, str]:
    """(exit code, stdout). Exit 2 denies; stdout may carry an "ask" decision."""
    denied, allowed = _policy(root)
    joined = command.replace("\\\n", "")  # the shell removes a backslash-newline
    flat = re.sub(r"[\"'\\]", "", joined)
    tool = bool(_CONTAINER_TOOL.search(flat))
    if tool:
        for token in re.findall(r"[A-Za-z0-9_.-]+", flat):
            if any(fnmatch.fnmatchcase(token, pattern) for pattern in denied):
                print(f"bash-guard: {token} is a denied container ({MANIFEST})", file=sys.stderr)
                return 2, ""
    segments, expansion = _scan(joined)
    sensitive = tool or bool(_GIT_WORD.search(flat))
    reasons: list[str] = []
    if _dynamic(segments) and (sensitive or expansion):
        reasons.append("the real command runs through a shell, eval, source, xargs or -exec")
    if sensitive and expansion:
        reasons.append("variables or substitutions next to git or docker")
    if tool and (
        re.search(r"(?<![\w-])DOCKER_[A-Z_]+=", joined)
        or any(os.environ.get(name) for name in _ENDPOINT_VARIABLES)
    ):
        reasons.append("a docker endpoint, context or config other than the default")
    for segment in segments:
        try:
            words = shlex.split(segment)
        except ValueError:
            if _GIT_WORD.search(re.sub(r"[\"'\\]", "", segment)) or _CONTAINER_TOOL.search(
                re.sub(r"[\"'\\]", "", segment)
            ):
                reasons.append("a command bash-guard could not parse")
            continue
        head = _command_word(words)
        if head is not None and re.search(r"[$`]", head):
            reasons.append("an executable chosen by a variable")
            continue
        for index, word in enumerate(words):
            name = Path(word).name
            if name == "git":
                reason = _git_reason(words[index:])
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
