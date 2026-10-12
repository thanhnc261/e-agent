"""Qualification must distinguish a business outcome from infrastructure failure."""

import importlib.util
from pathlib import Path

import pytest
from e_agent.erp.testing.scripted_tasks import ScriptedErpDriver


@pytest.fixture
def harness():
    path = Path(__file__).resolve().parents[3] / "scripts/qualify_model.py"
    spec = importlib.util.spec_from_file_location("qualification_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_infrastructure_failure_is_not_a_business_refusal(harness, monkeypatch):
    class BrokenDriver:
        driver_id = "fixture-infrastructure-failure"

        async def advance(self, *args):
            raise RuntimeError("CANARY-NOT-FOR-EVIDENCE")

    monkeypatch.setattr(harness, "ollama_model", lambda *args: None)
    monkeypatch.setattr(harness, "PydanticAiDriver", lambda *args, **kw: BrokenDriver())
    record = await harness.trial("over-budget", "fixture", "unused", 0)
    assert record["state"] == "ERROR" and not record["passed"]
    assert "CANARY-NOT-FOR-EVIDENCE" not in str(record)


async def test_unrelated_verified_answer_does_not_complete_a_po_task(harness, monkeypatch):
    monkeypatch.setattr(harness, "ollama_model", lambda *args: None)
    monkeypatch.setattr(
        harness,
        "PydanticAiDriver",
        lambda *args, **kw: ScriptedErpDriver(
            connection_id="conn-fixture-erp",
            task_kind="shortage",
        ),
    )
    record = await harness.trial("valid", "fixture", "unused", 0)
    assert record["state"] == "SUCCEEDED"
    assert record["verified_contracts"] == ["procurement.shortage.answer.v1"]
    assert not record["passed"]


async def test_admission_error_is_retained_as_a_failed_trial(harness, monkeypatch):
    async def broken(*args, **kw):
        raise ValueError("private configuration detail")

    monkeypatch.setattr(harness, "build_runtime", broken)
    record = await harness.trial("valid", "fixture", "unused", 0)
    assert record["state"] == "ERROR" and not record["passed"]
    assert record["reason"] == "ValueError"


def test_frozen_model_requires_observed_digest_and_context(harness):
    metadata = {"model_digest": "weights", "context_length": 32768, "ollama_version": "version"}
    report = {
        "model_digest": "weights",
        "required_context_length": 32768,
        "ollama_version": "version",
        "trials": [{"model_before": dict(metadata), "model_after": dict(metadata)}],
    }
    assert harness.stable_model(report)
    report["trials"][0]["model_after"]["context_length"] = 4096
    assert not harness.stable_model(report)
    report["trials"][0]["model_after"] = dict(metadata)
    report["trials"][0]["model_after"]["model_digest"] = "changed"
    assert not harness.stable_model(report)
    report["trials"] = []
    assert not harness.stable_model(report)
