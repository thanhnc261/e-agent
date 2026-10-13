import json
from pathlib import Path

import pytest
from e_agent_harness import gate


def _evidence_files(root: Path, task: str) -> list[Path]:
    return sorted((root / "harness" / "state" / "evidence" / "gates" / task).glob("*.json"))


def _set_gate(repo, old: str, new: str) -> None:
    manifest = repo.root / "harness/context.toml"
    text = manifest.read_text()
    assert old in text
    manifest.write_text(text.replace(old, new))


def test_gate_writes_evidence_tied_to_head_on_clean_tree(repo) -> None:
    result = repo.invoke("gate", "quick")
    assert result.code == 0, result
    files = _evidence_files(repo.root, "no-task")
    assert len(files) == 1
    doc = json.loads(files[0].read_text())
    assert doc["commit"] == repo.base
    assert doc["clean_tree"] is True
    assert doc["ok"] is True
    assert doc["commands"][0]["counts"] == {"passed": 3, "skipped": 1}
    assert str(files[0].relative_to(repo.root)) in result.out


def test_gate_records_dirty_tree_and_task_id(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    repo.write("src/pkg/new.py", "Y = 2\n")
    assert repo.invoke("gate", "quick").code == 0
    doc = json.loads(_evidence_files(repo.root, "1c.1")[0].read_text())
    assert doc["clean_tree"] is False
    assert doc["task"] == "1c.1"


def test_gate_stops_at_first_failure_and_exits_1(repo) -> None:
    _set_gate(
        repo,
        'full = ["echo full ok"]',
        'full = ["echo first", "python3 -c \'import sys; sys.exit(3)\'", "echo never"]',
    )
    result = repo.invoke("gate", "full")
    assert result.code == 1
    doc = json.loads(_evidence_files(repo.root, "no-task")[0].read_text())
    assert [c["exit_code"] for c in doc["commands"]] == [0, 3]
    assert doc["ok"] is False


def test_gate_times_out_and_records_124(repo) -> None:
    _set_gate(repo, 'pg = ["echo pg ok"]', 'pg = ["sleep 5"]')
    result = repo.invoke("gate", "pg", "--timeout", "1")
    assert result.code == 1
    doc = json.loads(_evidence_files(repo.root, "no-task")[0].read_text())
    assert doc["commands"][0]["exit_code"] == 124
    assert "timeout" in doc["commands"][0]["output_tail"]


def test_gate_redacts_secrets_in_evidence(repo) -> None:
    _set_gate(
        repo,
        'e2e = ["echo e2e ok"]',
        'e2e = ["echo password=hunter2 DSN postgresql://user:pw123@db/e_agent'
        ' api_key: sk-live-ZZ987"]',
    )
    assert repo.invoke("gate", "e2e").code == 0
    text = _evidence_files(repo.root, "no-task")[0].read_text()
    assert "hunter2" not in text and "pw123" not in text and "sk-live-ZZ987" not in text
    assert "[REDACTED]" in text


def test_gate_substitutes_package(repo) -> None:
    _set_gate(
        repo, "quick = [\"echo '3 passed, 1 skipped'\"]", 'quick = ["echo testing {package}"]'
    )
    assert repo.invoke("gate", "quick", "--package", "tests/unit/kernel").code == 0
    doc = json.loads(_evidence_files(repo.root, "no-task")[0].read_text())
    assert doc["commands"][0]["command"] == "echo testing tests/unit/kernel"
    assert "testing tests/unit/kernel" in doc["commands"][0]["output_tail"]


def test_live_check_writes_under_evidence_live(repo) -> None:
    result = repo.invoke("live-check")
    assert result.code == 0, result
    files = sorted((repo.root / "harness" / "state" / "evidence" / "live").glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["gate_set"] == "live"


def test_parse_counts_reads_pytest_summary() -> None:
    assert gate.parse_counts("== 12 passed, 2 skipped, 1 failed in 3s ==") == {
        "passed": 12,
        "skipped": 2,
        "failed": 1,
    }
    assert gate.parse_counts("no tests here") == {}


def test_output_tail_is_capped(repo) -> None:
    _set_gate(repo, 'full = ["echo full ok"]', 'full = ["seq 1 500"]')
    assert repo.invoke("gate", "full").code == 0
    doc = json.loads(_evidence_files(repo.root, "no-task")[0].read_text())
    assert doc["commands"][0]["output_tail"].splitlines()[-1] == "500"
    assert len(doc["commands"][0]["output_tail"].splitlines()) <= gate.TAIL_LINES


def test_redact_covers_bearer_json_and_cli_flags() -> None:
    samples = {
        "Authorization: Bearer sk-live-TOK1": "sk-live-TOK1",
        '{"password": "hunter2-J"}': "hunter2-J",
        "--password hunter2-F": "hunter2-F",
        "--api-key=sk-live-TOK2": "sk-live-TOK2",
        "export TOKEN=sk-live-TOK3": "sk-live-TOK3",
    }
    for text, secret in samples.items():
        redacted = gate.redact(text)
        assert secret not in redacted, (text, redacted)
        assert "[REDACTED]" in redacted


def test_gate_timeout_kills_the_whole_process_group(repo) -> None:
    import subprocess

    _set_gate(repo, 'pg = ["echo pg ok"]', 'pg = ["sleep 31.7"]')
    assert repo.invoke("gate", "pg", "--timeout", "1").code == 1
    leftover = subprocess.run(["pgrep", "-f", "sleep 31.7"], capture_output=True, text=True)
    assert leftover.returncode != 0, f"orphaned: {leftover.stdout}"


PG_GUARD = """
[gate_guards.pg]
require_env = ["E_AGENT_TEST_PG_DSN"]
distinct_databases = [["E_AGENT_TEST_PG_DSN", "E_AGENT_PG_DSN"]]
"""


def _guard_pg(repo) -> None:
    manifest = repo.root / "harness/context.toml"
    manifest.write_text(manifest.read_text() + PG_GUARD)


def test_pg_guard_refuses_missing_test_dsn(repo, monkeypatch) -> None:
    _guard_pg(repo)
    monkeypatch.delenv("E_AGENT_TEST_PG_DSN", raising=False)
    result = repo.invoke("gate", "pg")
    assert result.code == 1
    assert "E_AGENT_TEST_PG_DSN" in result.out and "refused" in result.out
    assert not (repo.root / "harness/state/evidence").exists()
    assert not (repo.root / "evidence").exists()


def test_pg_guard_refuses_same_database(repo, monkeypatch) -> None:
    _guard_pg(repo)
    monkeypatch.setenv("E_AGENT_PG_DSN", "postgresql://u:secret@db.local:5433/e_agent")
    monkeypatch.setenv("E_AGENT_TEST_PG_DSN", "postgresql://u:secret@db.local:5433/e_agent")
    result = repo.invoke("gate", "pg")
    assert result.code == 1
    assert "same database" in result.out
    assert "secret" not in result.out


def test_pg_guard_compares_parsed_databases(repo, monkeypatch) -> None:
    _guard_pg(repo)
    monkeypatch.setenv("E_AGENT_PG_DSN", "postgresql://u@localhost/e_agent")
    monkeypatch.setenv("E_AGENT_TEST_PG_DSN", "host=localhost port=5432 dbname=e_agent user=t")
    assert repo.invoke("gate", "pg").code == 1
    assert gate.database_name("postgresql://u@h:5433/db") == "db"
    assert gate.database_name("dbname=db host=h") == "db"
    assert gate.database_name("postgresql:///db") == "db"


@pytest.mark.parametrize(
    "test_dsn",
    [
        "host=localhost dbname='e_agent' user=u",  # quoted keyword value
        "host = localhost dbname = e_agent",  # spaces around '='
        "postgresql://u@localhost/e%5Fagent",  # percent-encoded name
        "postgresql://u@localhost/other?dbname=e_agent",  # query override
        "postgresql://u@other-host:6543/e_agent",  # same name on another host: refused anyway
    ],
)
def test_pg_guard_refuses_every_spelling_of_the_live_database(repo, monkeypatch, test_dsn) -> None:
    _guard_pg(repo)
    monkeypatch.setenv("E_AGENT_PG_DSN", "postgresql://u@localhost/e_agent")
    monkeypatch.setenv("E_AGENT_TEST_PG_DSN", test_dsn)
    result = repo.invoke("gate", "pg")
    assert result.code == 1, test_dsn
    assert "refused" in result.out


@pytest.mark.parametrize(
    "test_dsn", ["postgresql://u@localhost", "host=localhost user=u", "not a dsn"]
)
def test_pg_guard_refuses_a_test_dsn_without_a_database_name(repo, monkeypatch, test_dsn) -> None:
    _guard_pg(repo)
    monkeypatch.setenv("E_AGENT_PG_DSN", "postgresql://u@localhost/e_agent")
    monkeypatch.setenv("E_AGENT_TEST_PG_DSN", test_dsn)
    result = repo.invoke("gate", "pg")
    assert result.code == 1
    assert "cannot tell" in result.out


def test_wildcard_guard_protects_every_gate_set(repo, monkeypatch) -> None:
    manifest = repo.root / "harness/context.toml"
    manifest.write_text(
        manifest.read_text()
        + '\n[gate_guards."*"]\ndistinct_databases = [["E_AGENT_TEST_PG_DSN", "E_AGENT_PG_DSN"]]\n'
    )
    monkeypatch.setenv("E_AGENT_PG_DSN", "postgresql://u@localhost/e_agent")
    monkeypatch.setenv("E_AGENT_TEST_PG_DSN", "postgresql://u@localhost/e_agent")
    for set_name in ("full", "quick"):
        result = repo.invoke("gate", set_name)
        assert result.code == 1, set_name
        assert "same database" in result.out
    monkeypatch.delenv("E_AGENT_TEST_PG_DSN")
    assert repo.invoke("gate", "full").code == 0  # no test DSN: Postgres tests skip


def test_redact_authorization_schemes_and_escaped_json() -> None:
    samples = {
        "Authorization: Basic c3ludGhldGljLUJBU0lD": "c3ludGhldGljLUJBU0lD",
        "authorization=Digest username-DIGEST-SECRET": "DIGEST-SECRET",
        '{"password": "ab\\"cd-JSON-SECRET"}': "cd-JSON-SECRET",
        "PASSWORD='quote\\'d-SINGLE-SECRET'": "SINGLE-SECRET",
    }
    for text, secret in samples.items():
        redacted = gate.redact(text)
        assert secret not in redacted, (text, redacted)


def test_pg_guard_allows_distinct_databases(repo, monkeypatch) -> None:
    _guard_pg(repo)
    monkeypatch.setenv("E_AGENT_PG_DSN", "postgresql://u@localhost:5432/e_agent")
    monkeypatch.setenv("E_AGENT_TEST_PG_DSN", "postgresql://u@localhost:5432/e_agent_test")
    result = repo.invoke("gate", "pg")
    assert result.code == 0, result


def test_gates_without_guards_are_unaffected(repo, monkeypatch) -> None:
    _guard_pg(repo)
    monkeypatch.delenv("E_AGENT_TEST_PG_DSN", raising=False)
    assert repo.invoke("gate", "quick").code == 0


def test_gate_writes_committable_evidence(repo) -> None:
    result = repo.invoke("gate", "quick")
    assert result.code == 0, result
    assert "harness/state/evidence/gates/no-task/" in result.out
    assert not (repo.root / "evidence").exists()


def test_second_gate_ignores_uncommitted_evidence(repo) -> None:
    assert repo.invoke("gate", "quick").code == 0
    assert repo.invoke("gate", "full").code == 0
    docs = [json.loads(f.read_text()) for f in _evidence_files(repo.root, "no-task")]
    assert len(docs) == 2
    assert all(d["clean_tree"] for d in docs)
    repo.write("src/pkg/mod.py", "X = 99\n")
    assert repo.invoke("gate", "pg").code == 0
    latest = [json.loads(f.read_text()) for f in _evidence_files(repo.root, "no-task")]
    assert [d["clean_tree"] for d in latest if d["gate_set"] == "pg"] == [False]


def test_two_runs_in_one_second_keep_both_files(repo) -> None:
    from datetime import UTC, datetime

    from e_agent_harness import manifest as mf
    from e_agent_harness import state

    paths = state.Paths(repo.root)
    m = mf.load_manifest(paths.manifest)
    now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=UTC)
    first = gate.write_evidence(
        paths.evidence("t"), gate.run_gate(m, "quick", repo.root, task_id="t", now=now)
    )
    second = gate.write_evidence(
        paths.evidence("t"), gate.run_gate(m, "quick", repo.root, task_id="t", now=now)
    )
    assert first != second and first.exists() and second.exists()
