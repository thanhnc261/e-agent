from datetime import UTC, datetime, timedelta, timezone

import pytest
from e_agent.contracts.action import ALLOWED_ACTION_TRANSITIONS, ActionState
from e_agent.contracts.capability import CapabilityDescriptor, EffectKind
from e_agent.contracts.common import DecimalStr, Record, UtcDatetime, format_decimal
from e_agent.contracts.connection import ConnectionDescriptor, ConnectionOwnership
from e_agent.contracts.events import RunEvent, RunEventType
from pydantic import ValidationError


class _Money(Record):
    amount: DecimalStr


class _Stamp(Record):
    at: UtcDatetime


def test_decimal_strings_are_canonical() -> None:
    assert _Money(amount="7.500").amount == "7.5"
    assert _Money(amount="-0.00").amount == "0"
    assert _Money(amount="1E+2").amount == "100"
    with pytest.raises(ValidationError):
        _Money(amount="NaN")
    with pytest.raises(ValidationError):
        _Money(amount=7.5)  # type: ignore[arg-type]


def test_format_decimal_rejects_infinity() -> None:
    from decimal import Decimal

    with pytest.raises(ValueError, match="NaN"):
        format_decimal(Decimal("Infinity"))


def test_timestamps_must_be_aware_and_serialize_as_utc_z() -> None:
    with pytest.raises(ValidationError):
        _Stamp(at=datetime(2026, 10, 6, 12, 0))
    local = datetime(2026, 10, 6, 19, 0, tzinfo=timezone(timedelta(hours=7)))
    stamp = _Stamp(at=local)
    assert stamp.at == datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    assert stamp.model_dump(mode="json")["at"] == "2026-10-06T12:00:00.000000Z"


def test_records_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _Money(amount="1", extra="x")  # type: ignore[call-arg]


def test_capability_ids_follow_bounded_context_naming() -> None:
    cap = CapabilityDescriptor(
        contract_id="procurement.purchase-order.create-draft.v1",
        effect=EffectKind.WRITE,
        input_schema_id="in",
        output_schema_id="out",
    )
    assert cap.bounded_context == "procurement"
    with pytest.raises(ValidationError):
        CapabilityDescriptor(
            contract_id="CreatePO",
            effect=EffectKind.WRITE,
            input_schema_id="i",
            output_schema_id="o",
        )


def test_connection_ownership_rules() -> None:
    shared = ConnectionDescriptor(
        tenant_id="t1",
        connection_id="c1",
        version=2,
        integration_id="fixture",
        ownership=ConnectionOwnership.TENANT_SHARED,
        provider_subject="svc",
    )
    assert shared.credential_subject() == "c1@2/svc"
    with pytest.raises(ValidationError):
        ConnectionDescriptor(
            tenant_id="t1",
            connection_id="c2",
            version=1,
            integration_id="fixture",
            ownership=ConnectionOwnership.USER_DELEGATED,
        )


def test_terminal_action_states_have_no_exits() -> None:
    for state in (ActionState.VERIFIED, ActionState.FAILED, ActionState.BLOCKED):
        assert ALLOWED_ACTION_TRANSITIONS[state] == frozenset()
    # UNKNOWN must never transition back to a dispatchable state (no blind replay).
    assert ActionState.DISPATCHING not in ALLOWED_ACTION_TRANSITIONS[ActionState.UNKNOWN]


def test_event_catalog_round_trip() -> None:
    event = RunEvent(
        event_id="evt_1",
        tenant_id="t1",
        run_id="run_1",
        sequence=1,
        type=RunEventType.RUN_CREATED,
        occurred_at=datetime(2026, 10, 6, tzinfo=UTC),
    )
    data = event.model_dump(mode="json")
    assert data["type"] == "run.created"
    assert RunEvent.model_validate(data) == event
