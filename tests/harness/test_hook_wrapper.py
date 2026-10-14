"""The Claude Code hook entry script (.claude/hooks/harness_hook.py), run as Claude Code runs it."""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "harness_hook.py"


def hook(args: list[str], payload: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        timeout=120,
    )


def _activate(repo) -> None:
    assert (
        repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/pkg/**").code == 0
    )


def _write(repo, path: str, cwd: Path | None = None) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": path},
        "cwd": str(cwd or repo.root),
    }


def test_wrapper_denies_out_of_scope_write(repo) -> None:
    _activate(repo)
    result = hook(["check-scope", "--hook"], _write(repo, str(repo.root / "docs/other.md")))
    assert result.returncode == 2, result
    assert "outside the task's allowed paths" in result.stderr


def test_wrapper_allows_in_scope_write(repo) -> None:
    _activate(repo)
    result = hook(["check-scope", "--hook"], _write(repo, "src/pkg/mod.py"))
    assert result.returncode == 0, result


def test_wrapper_uses_the_payload_cwd_repository(repo, tmp_path) -> None:
    _activate(repo)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    # The hook process starts somewhere else; the payload cwd is a subdirectory of the repo.
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "check-scope", "--hook"],
        input=json.dumps(_write(repo, str(repo.root / "archive/old.md"), cwd=repo.root / "src")),
        capture_output=True,
        text=True,
        cwd=elsewhere,
        timeout=120,
    )
    assert result.returncode == 2
    assert "protected path" in result.stderr


def test_wrapper_status_prints_sessionstart_json(repo) -> None:
    payload = {"hook_event_name": "SessionStart", "source": "startup", "cwd": str(repo.root)}
    result = hook(["status", "--format", "hook"], payload)
    assert result.returncode == 0, result
    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    assert "new-task" in out["additionalContext"]


def test_wrapper_checkpoint_appends_an_entry(repo) -> None:
    payload = {"hook_event_name": "PreCompact", "session_id": "s-hook", "cwd": str(repo.root)}
    result = hook(["checkpoint", "--hook"], payload)
    assert result.returncode == 0, result
    assert "s-hook" in (repo.root / "harness/state/progress.md").read_text()


def test_wrapper_failure_modes(repo, tmp_path) -> None:
    outside = tmp_path / "no-repo"
    outside.mkdir()
    payload = _write(repo, "x.py", cwd=outside)
    denied = hook(["check-scope", "--hook"], payload)
    assert denied.returncode == 2
    assert "no repository" in denied.stderr
    for args in (
        ["status", "--format", "hook"],
        ["checkpoint", "--hook"],
        ["close-check", "--hook"],
    ):
        assert hook(args, payload).returncode == 0, args
    # uv missing in a uv project: check-scope still fails closed, the others stay silent.
    (repo.root / "pyproject.toml").write_text("[project]\nname = 'x'\nversion = '0'\n")
    no_uv = {"PATH": "/nonexistent"}
    assert hook(["check-scope", "--hook"], _write(repo, "src/pkg/mod.py"), no_uv).returncode == 2
    status_payload = {"hook_event_name": "SessionStart", "cwd": str(repo.root)}
    assert hook(["status", "--format", "hook"], status_payload, no_uv).returncode == 0
    unattended = {**no_uv, "E_AGENT_HARNESS_UNATTENDED": "1"}
    stop = {"hook_event_name": "Stop", "stop_hook_active": False, "cwd": str(repo.root)}
    assert hook(["close-check", "--hook"], stop, unattended).returncode == 2


def test_wrapper_has_no_format_mode(repo) -> None:
    script = SCRIPT.read_text()
    assert '"format"' not in script and "ruff" not in script


def test_stop_hook_spawns_nothing_when_attended(repo, tmp_path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "uv-was-called"
    fake_uv = bin_dir / "uv"
    fake_uv.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
    fake_uv.chmod(0o755)
    (repo.root / "pyproject.toml").write_text("[project]\nname = 'x'\nversion = '0'\n")
    env = {k: v for k, v in os.environ.items() if k != "E_AGENT_HARNESS_UNATTENDED"}
    env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
    stop = {"hook_event_name": "Stop", "stop_hook_active": False, "cwd": str(repo.root)}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "close-check", "--hook"],
        input=json.dumps(stop),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0
    assert not marker.exists(), "an attended Stop must not start the harness"


def _bash(
    repo, command: str, cwd: Path | None = None, env: dict | None = None
) -> subprocess.CompletedProcess:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd or repo.root),
    }
    return hook(["bash-guard"], payload, env=env)


def _fake_docker(folder: Path, names: str, code: int = 0) -> dict:
    """A docker on PATH that answers the compose label query with ``names``."""
    folder.mkdir(parents=True, exist_ok=True)
    fake = folder / "docker"
    fake.write_text(
        f'#!/bin/sh\necho "$@" >> "{folder}/calls"\nprintf "%s" "{names}"\nexit {code}\n'
    )
    fake.chmod(0o755)
    return {"PATH": f"{folder}:{os.environ['PATH']}"}


SANDBOX_NAMES = "odoo19-learning-odoo-1\nodoo19-learning-db-1\n"


def test_bash_guard_denies_docker_on_a_denied_container(repo) -> None:
    for command in (
        "/usr/local/bin/docker stop odoo-bench-db-1",
        "docker compose --project-name=odoo-bench down",
        "docker compose -p odoo-bench down",
        "sudo docker exec -it odoo-bench-odoo-1 bash",
        "ls && docker kill odoo-bench-db-1",
        "DOCKER_HOST=unix:///x docker rm odoo-bench-db-1",
        "echo $(docker restart odoo-bench-odoo-1)",
    ):
        result = _bash(repo, command)
        assert result.returncode == 2, command
        assert "odoo-bench" in result.stderr


def test_bash_guard_lets_other_commands_through(repo) -> None:
    for command in (
        "docker exec odoo19-learning-odoo-1 odoo --version",
        "grep -rn odoo-bench docs",
        "git status",
        "git reset --soft HEAD~1",
        "git log --grep push",
    ):
        result = _bash(repo, command)
        assert result.returncode == 0, command
        assert result.stdout == "", command


def test_bash_guard_asks_before_integration_commands(repo) -> None:
    for command in (
        "git push",
        "git -C . push origin main",
        "git -c core.pager=cat push",
        "git --no-pager merge feature",
        "cd sub && git rebase main",
        "git reset HEAD~1 --hard",
        "git --git-dir=.git reset --hard",
    ):
        result = _bash(repo, command)
        assert result.returncode == 0, command
        decision = json.loads(result.stdout)["hookSpecificOutput"]
        assert decision["hookEventName"] == "PreToolUse"
        assert decision["permissionDecision"] == "ask", command


def _decision_of(result: subprocess.CompletedProcess) -> str:
    if result.returncode == 2:
        return "deny"
    if result.stdout.strip():
        return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]
    return "none"


def test_bash_guard_denies_dynamic_forms_that_name_a_denied_container(repo) -> None:
    for command in (
        "bash -c 'docker stop odoo-bench-db-1'",
        "eval docker kill odoo-bench-db-1",
        "/usr/local/bin/docker stop \\\nodoo-bench-db-1",
        "git -C . push origin HEAD; /usr/local/bin/docker stop odoo-bench-db-1",  # deny wins
    ):
        assert _decision_of(_bash(repo, command)) == "deny", command


def test_bash_guard_asks_where_it_cannot_see_the_real_command(repo) -> None:
    from tests.harness.conftest import git

    git(repo.root, "config", "alias.shipit", "push")
    for command in (
        "git -c alias.x=push x origin HEAD",
        "git -c alias.x='!git push' x",
        "git shipit origin HEAD",  # an alias from the repository config
        "sudo -u me git push",
        r"find . -name x -exec git push \;",
        "echo main | xargs -I{} git push origin {}",
        "bash -c 'git push origin main'",
        "docker stop production-db-1",  # not an allowed container
        "docker --context production stop odoo19-learning-db-1",
        "DOCKER_HOST=tcp://remote:2375 docker ps",
        "docker compose -p other up -d",
    ):
        assert _decision_of(_bash(repo, command)) == "ask", command


def test_bash_guard_allows_ordinary_commands(repo) -> None:
    for command in (
        "docker ps",
        "docker exec -it odoo19-learning-odoo-1 bash",
        "docker compose -p odoo19-learning ps",
        "docker logs --tail 20 odoo19-learning-odoo-1",
        "grep -rn odoo-bench docs",
        "git status",
        "git log --grep push",
        "git commit -m 'push the button'",
    ):
        assert _decision_of(_bash(repo, command)) == "none", command


def test_bash_guard_keeps_its_policy_outside_the_repository(repo, tmp_path) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    result = _bash(repo, "/usr/local/bin/docker stop odoo-bench-db-1", cwd=outside)
    assert _decision_of(result) == "deny"


def test_r3_quoting_cannot_hide_a_denied_container(repo) -> None:
    for command in (
        '/usr/local/bin/docker stop odoo19-learning-db-1 odoo-"bench"-db-1',
        '/usr/local/bin/do"cker" stop odoo-bench-db-1',
        "docker stop odoo-\\bench-db-1",
    ):
        assert _decision_of(_bash(repo, command)) == "deny", command


def test_r3_uncertain_commands_ask(repo) -> None:
    from tests.harness.conftest import git

    git(repo.root, "config", "alias.ship2", "-c core.pager=cat push")
    for command in (
        "bash --noprofile -c 'git -C . push origin HEAD'",
        "bash -e -c 'git push'",
        'bash -c "$SCRIPT"',
        "git -c Alias.reviewprobe=push reviewprobe origin HEAD",
        "git ship2 origin HEAD",
        "git -C /tmp/other anyalias",
        "git pull",
        "docker stop odoo19-learning-db-1 production-db-1",
        "docker exec --env odoo19-learning-db-1 production-db-1 true",
        "docker container stop production-db-1",
        "docker -Htcp://remote:2375 stop odoo19-learning-db-1",
        "docker --config /other/config stop odoo19-learning-db-1",
        "docker run --rm alpine true",
        "docker logs $(docker ps -q)",
    ):
        assert _decision_of(_bash(repo, command)) == "ask", command


def test_r3_fully_parsed_commands_pass(repo) -> None:
    for command in (
        "docker ps",
        "docker container ls",
        "docker exec -it odoo19-learning-odoo-1 bash",
        "docker container stop odoo19-learning-db-1",
        "docker stop -t 5 odoo19-learning-db-1 e-agent-ledger",
        "docker compose -p odoo19-learning ps",
        "docker logs --tail 20 odoo19-learning-odoo-1",
        "git --no-pager log --oneline",
        r"find . -name '*.py' -exec grep -l TODO {} \;",
    ):
        assert _decision_of(_bash(repo, command)) == "none", command


def test_r4_shell_semantics_ask(repo) -> None:
    for command in (
        "gi\\\nt push origin HEAD",  # the shell removes a backslash-newline inside a word
        "gi\"t\" -c 'core.pager=cat;cat' push origin HEAD",
        '"$TOOL" push origin HEAD',
        'command eval "$SCRIPT"',
        "git submodule foreach git push origin HEAD",
        "docker exec odoo19-learning-odoo-1 git push origin HEAD",
        "git reset --ha HEAD",
        "git reset --keep HEAD~1",
        "export DOCKER_HOST=tcp://remote:2375; docker exec odoo19-learning-db-1 true",
        "docker compose -p odoo19-learning run --name production-db-1 db true",
        "docker compose -p odoo19-learning -f other.yml up -d",
    ):
        assert _decision_of(_bash(repo, command)) == "ask", command


def test_r4_inherited_docker_endpoint_asks(repo) -> None:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "docker exec odoo19-learning-db-1 true"},
        "cwd": str(repo.root),
    }
    result = hook(["bash-guard"], payload, env={"DOCKER_HOST": "tcp://remote:2375"})
    assert _decision_of(result) == "ask"


def test_r4_literal_punctuation_passes(repo, tmp_path) -> None:
    sandbox = _fake_docker(tmp_path / "bin", SANDBOX_NAMES)
    for command in (
        "git log -1 --format='%h (%s)'",
        "git commit -m 'fix: a & b; c | d'",
        "git commit -m 'costs $5 (approx)'",
        "git reset --soft HEAD~1",
        "docker compose -p odoo19-learning logs --tail 20 odoo",
        "docker compose -p odoo19-learning ps odoo",
        "docker exec odoo19-learning-odoo-1 odoo --version",
    ):
        assert _decision_of(_bash(repo, command, env=sandbox)) == "none", command


def test_r5_ordinary_variants_ask(repo) -> None:
    for command in (
        'sudo -n "$DOCKER_BIN" stop production-db-1',
        "sudo -nE docker stop production-db-1",  # combined flags: arity unknown
        "env -S 'git push origin HEAD'",
        "git submodule --quiet foreach 'git push origin HEAD'",
        "git bisect start && git bisect --no-checkout run ./probe.sh",
        "COMPOSE_FILE=/tmp/other.yml docker compose -p odoo19-learning ps",
        "export COMPOSE_FILE=/tmp/other.yml; docker compose -p odoo19-learning ps",
        "timeout 5 eval git push",
    ):
        assert _decision_of(_bash(repo, command)) == "ask", command


def test_r5_inherited_compose_file_asks(repo) -> None:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "docker compose -p odoo19-learning ps"},
        "cwd": str(repo.root),
    }
    result = hook(["bash-guard"], payload, env={"COMPOSE_FILE": "/tmp/other.yml"})
    assert _decision_of(result) == "ask"


def test_r5_literal_words_pass(repo) -> None:
    for command in (
        "git log --grep 'source'",
        "git commit -m 'fix source path'",
        "git log --grep source -1",
        "env -u PAGER docker ps",
        "nice -n 10 git status",
        "nice -10 git status",
    ):
        assert _decision_of(_bash(repo, command)) == "none", command


def test_r5_wrapper_times_out_before_the_host(repo, tmp_path) -> None:
    """A stalled harness ends inside the wrapper, which then denies check-scope itself."""
    import importlib.util
    import io

    spec = importlib.util.spec_from_file_location("harness_hook_r5", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TIMEOUT = 0.5
    module._runner = lambda root: [sys.executable, "-c", "import time; time.sleep(5)"]
    stdin, sys.stdin = sys.stdin, io.StringIO(json.dumps(_write(repo, "src/pkg/mod.py")))
    try:
        assert module.main(["check-scope", "--hook"]) == 2
    finally:
        sys.stdin = stdin


def _guard_in(repo, command: str, cwd: Path, env: dict | None = None) -> str:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
    }
    return _decision_of(hook(["bash-guard"], payload, env=env))


def test_r6_bash_guard_on_an_old_python_denies(repo) -> None:
    import shutil

    old = shutil.which("python3.9") or "/usr/bin/python3"
    version = subprocess.run(
        [old, "-c", "import sys; print(sys.version_info[:2] < (3, 11))"],
        capture_output=True,
        text=True,
        check=False,
    )
    if version.stdout.strip() != "True":
        import pytest

        pytest.skip("no Python older than 3.11 on this machine")
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git status"},
        "cwd": str(repo.root),
    }
    result = subprocess.run(
        [old, str(SCRIPT), "bash-guard"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 2, result
    assert "Python 3.11" in result.stderr


def test_r9_compose_lifecycle_asks_without_querying(repo, tmp_path) -> None:
    """Compose acts on the project's existing containers, not on names in the command."""
    env = _fake_docker(tmp_path / "bin", SANDBOX_NAMES)
    for sub in ("stop", "start", "restart odoo", "pause", "unpause"):
        command = f"docker compose -p odoo19-learning {sub}"
        assert _decision_of(_bash(repo, command, env=env)) == "ask", command
    for sub in ("ps", "logs --tail 20 odoo", "top", "images", "ls", "version", "config"):
        command = f"docker compose -p odoo19-learning {sub}"
        assert _decision_of(_bash(repo, command, env=env)) == "none", command
    assert not (tmp_path / "bin" / "calls").exists()  # the hook never calls the daemon


def test_r7_docker_under_another_home_or_user_asks(repo, tmp_path) -> None:
    sandbox = _fake_docker(tmp_path / "bin", SANDBOX_NAMES)
    for command in (
        "HOME=/Users/other docker exec odoo19-learning-odoo-1 odoo --version",
        "export HOME=/Users/other; docker exec odoo19-learning-odoo-1 true",
        "sudo -H docker exec odoo19-learning-odoo-1 true",
        "sudo -u other docker compose -p odoo19-learning ps",
    ):
        assert _decision_of(_bash(repo, command, env=sandbox)) == "ask", command


def test_r6_persisted_remote_docker_context_asks(repo, tmp_path) -> None:
    import hashlib

    home = tmp_path / "home"
    meta = home / ".docker" / "contexts" / "meta"
    for name, host in (("remote", "tcp://build-server:2376"), ("desktop-linux", "unix:///x.sock")):
        folder = meta / hashlib.sha256(name.encode()).hexdigest()
        folder.mkdir(parents=True)
        (folder / "meta.json").write_text(
            json.dumps({"Name": name, "Endpoints": {"docker": {"Host": host}}})
        )
    config = home / ".docker" / "config.json"
    command = "docker exec odoo19-learning-odoo-1 odoo --version"
    config.write_text(json.dumps({"currentContext": "remote"}))
    assert _guard_in(repo, command, repo.root, {"HOME": str(home)}) == "ask"
    config.write_text(json.dumps({"currentContext": "desktop-linux"}))
    assert _guard_in(repo, command, repo.root, {"HOME": str(home)}) == "none"
    config.write_text(json.dumps({"currentContext": "missing"}))
    assert _guard_in(repo, command, repo.root, {"HOME": str(home)}) == "ask"
    config.write_text("{}")
    assert _guard_in(repo, command, repo.root, {"HOME": str(home)}) == "none"


def test_r8_podman_compose_asks(repo, tmp_path) -> None:
    env = _fake_docker(tmp_path / "bin", SANDBOX_NAMES)
    command = "podman compose -p odoo19-learning ps"
    assert _decision_of(_bash(repo, command, env=env)) == "ask"
    assert not (tmp_path / "bin" / "calls").exists()


def test_r10_silent_pass_list_is_narrowed(repo) -> None:
    for command in (
        "git difftool --no-index --no-prompt --extcmd 'git push origin HEAD; true' a b",
        "git difftool -x 'git push' a b",
        "git -c core.pager='git push' log",
        "git --exec-path=/tmp/evil status",
        "git --config-env=core.pager=X log",
        "git clone --upload-pack='git push' ../repo out",
        "git clone -u 'git push' ../repo out",
        "git clone -c core.sshCommand=x ../repo out",
        "git fetch --upload='git push' origin",
        "git ls-remote --upload-pack=x origin",
        "git archive --remote=origin --exec=x HEAD",
        "git grep -O'git push' TODO",
        "git grep --open-files-in-pager=x TODO",
        "git diff --ext-diff",
        "git config core.pager 'git push'",
        "git config --global alias.x '!git push'",
        "git config set core.pager x",
        "git maintenance start",
        "CONTAINER_HOST=ssh://production/run/podman/podman.sock podman stop odoo19-learning-db-1",
        "podman exec odoo19-learning-db-1 true",
        "GIT_EXTERNAL_DIFF='git push' git diff",
        "EDITOR='git push' git commit",
        "export GIT_PAGER='git push'; git log",
        "PATH=/tmp/evil:$PATH docker ps",
        "GIT_SSH_COMMAND=x; git fetch",
    ):
        assert _decision_of(_bash(repo, command)) == "ask", command


def test_r10_ordinary_commands_still_pass(repo) -> None:
    for command in (
        "git config --get user.email",
        "git config --list --show-origin",
        "git config get user.name",
        "git clone --depth 1 ../repo out",
        "git fetch origin",
        "git grep -n TODO",
        "git diff --no-ext-diff HEAD~1",
        "git log --oneline -5",
        "git cherry-pick -x abc123",
        "set -o pipefail; git status --short",
        "docker ps --format '{{.Names}}'",
    ):
        assert _decision_of(_bash(repo, command)) == "none", command


def test_r11_option_operand_does_not_end_the_scan(repo) -> None:
    for command in (
        "git grep -e -- --open-files-in-pager='git push origin HEAD; true' -- README.md",
        "git grep -e -- -O'git push' -- README.md",
        "git grep -e -- --open='git push' -- README.md",
        "git log -S -- --ext-diff",
    ):
        assert _decision_of(_bash(repo, command)) == "ask", command
    assert _decision_of(_bash(repo, "git grep -n TODO -- src")) == "none"
