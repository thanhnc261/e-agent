import json
from pathlib import Path

from e_agent_harness import gate


def _evidence_files(root: Path, task: str) -> list[Path]:
    return sorted((root / "evidence" / "gates" / task).glob("*.json"))


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
    assert repo.invoke("gate", "quick", "--package", "packages/kernel").code == 0
    doc = json.loads(_evidence_files(repo.root, "no-task")[0].read_text())
    assert doc["commands"][0]["command"] == "echo testing packages/kernel"
    assert "testing packages/kernel" in doc["commands"][0]["output_tail"]


def test_live_check_writes_under_evidence_live(repo) -> None:
    result = repo.invoke("live-check")
    assert result.code == 0, result
    files = sorted((repo.root / "evidence" / "live").glob("*.json"))
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
