"""The Conversation records and RunRecord.conversation_id (ADR 0023 §2)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from e_agent.contracts.conversation import (
    CarriedAnswer,
    CarriedRef,
    CarriedRun,
    Conversation,
    MessageRoute,
    RouteKind,
)
from e_agent.contracts.features import FeatureMode, MemberFeatures
from e_agent.contracts.run import RunRecord, RunState
from e_agent.kernel.reconstruct import run_created_keys
from pydantic import ValidationError

NOW = datetime(2026, 10, 20, tzinfo=UTC)


def _run(**extra: object) -> RunRecord:
    return RunRecord(
        run_id="r1",
        tenant_id="t",
        requester_id="u",
        task="x",
        state=RunState.CREATED,
        revision=1,
        logical_operation_id="op",
        created_at=NOW,
        **extra,  # type: ignore[arg-type]
    )


def test_conversation_record_holds_no_text() -> None:
    assert set(Conversation.model_fields) == {
        "tenant_id",
        "conversation_id",
        "owner_id",
        "revision",
        "created_at",
        "updated_at",
    }


def test_carried_run_has_no_model_text_field() -> None:
    assert set(CarriedRun.model_fields) == {
        "run_id",
        "task_id",
        "task_version",
        "state",
        "reason_code",
        "user_messages",
        "answers",
        "refs",
    }
    assert set(CarriedRef.model_fields) == {"contract_id", "source_ref", "revision", "observed_at"}


def test_carried_answer_holds_only_declared_paths() -> None:
    assert set(CarriedAnswer.model_fields) == {"contract_id", "arguments"}
    with pytest.raises(ValidationError):
        CarriedAnswer(contract_id="c", arguments={}, summary="text")  # type: ignore[call-arg]


def test_message_route_answer_needs_run_and_revision() -> None:
    with pytest.raises(ValidationError):
        MessageRoute(kind=RouteKind.ANSWER, run_id="r1")
    with pytest.raises(ValidationError):
        MessageRoute(kind=RouteKind.ANSWER, run_revision=2)
    assert MessageRoute(kind=RouteKind.ANSWER, run_id="r1", run_revision=2).run_id == "r1"
    assert MessageRoute(kind=RouteKind.START).run_id is None
    with pytest.raises(ValidationError):
        MessageRoute(kind=RouteKind.REFUSE)
    assert MessageRoute(kind=RouteKind.REFUSE, hint="wait").hint == "wait"


def test_member_features_has_only_conversations() -> None:
    assert list(MemberFeatures.model_fields) == ["conversations"]
    assert MemberFeatures().conversations is FeatureMode.OFF


def test_run_record_conversation_id_defaults_none() -> None:
    assert _run().conversation_id is None
    assert _run(conversation_id="c1").conversation_id == "c1"


def test_run_created_has_no_conversation_key_when_unset() -> None:
    assert "conversation_id" not in run_created_keys(_run())
    assert run_created_keys(_run(conversation_id="c1"))["conversation_id"] == "c1"
