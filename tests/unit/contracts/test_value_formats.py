"""Host-side answer value formats (ADR 0023 §7, D17, Task 4c.4): the closed format set,
what a value must be to pass, and the descriptor rule that only answers declare formats."""

import copy
import json
import pickle
from typing import Any

import pytest
from e_agent.contracts.capability import CapabilityDescriptor, EffectKind
from e_agent.contracts.value_formats import FormatKind, ValueFormat, parse_format, value_passes
from pydantic import ValidationError

CLOSED_SET = {
    "decimal": ValueFormat(kind=FormatKind.DECIMAL),
    "integer": ValueFormat(kind=FormatKind.INTEGER),
    "date": ValueFormat(kind=FormatKind.DATE),
    "date-time": ValueFormat(kind=FormatKind.DATE_TIME),
    "ref": ValueFormat(kind=FormatKind.REF),
    "enum:open|late": ValueFormat(kind=FormatKind.ENUM, values=("open", "late")),
    "enum:one": ValueFormat(kind=FormatKind.ENUM, values=("one",)),
}


def test_every_format_in_the_closed_set_parses() -> None:
    for text, expected in CLOSED_SET.items():
        assert parse_format(text) == expected, text
    print(f"formats parsed: {len(CLOSED_SET)}")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "string",
        "Decimal",
        "number",
        "date_time",
        "uuid",
        "ref ",
        "enum",
        "enum:",
        "enum:a|",
        "enum:|a",
        "enum:a||b",
        "enum:a|a",
        "pattern:^x$",
        "enum: a",
        "enum:a\nb",
        "enum:open| late",
        "enum:a\u200bb",
    ],
)
def test_unknown_format_is_refused(text: str) -> None:
    with pytest.raises(ValueError, match="value format"):
        parse_format(text)


PASSING: dict[str, list[Any]] = {
    "decimal": [0, 3, -2.5, "12.5", "0", "-3", "1000"],
    "integer": [0, 7, -12],
    "date": ["2026-10-20", "2024-02-29"],
    "date-time": ["2026-10-20T08:30:00Z", "2026-10-20T08:30:00.125+07:00", "2026-10-20t08:30:00z"],
    "enum:open|late": ["open", "late"],
    "ref": ["SO0042", "odoo:sale.order/42", "x" * 256],
}
FAILING: dict[str, list[Any]] = {
    "decimal": [
        True,
        float("nan"),
        float("inf"),
        "12.50",
        "1e2",
        "+5",
        " 1",
        "-0",
        "1_000",
        "NaN",
        "",
        "abc",
        [],
        None,
    ],
    "integer": [True, False, 3.0, "3", 2.5, None],
    "date": ["20261020", "2026-02-30", "2026-10-20T00:00:00Z", "2026-W43-2", "", 20261020, None],
    "date-time": [
        "2026-10-20T08:30:00",
        "2026-10-20",
        "20261020T083000Z",
        "2026-10-20T25:00:00Z",
        "2026-10-20 08:30:00Z",
        1_700_000_000,
        None,
    ],
    "enum:open|late": ["Open", "", "closed", 1, None],
    "ref": [
        "",
        "x" * 257,
        "SO 42",
        "SO42\n",
        "\tSO42",
        "SO\x0042",
        "SO\u00a042",
        "SO\u200b42",  # zero-width space (Cf)
        "SO42\u202e",  # right-to-left override (Cf)
        42,
        None,
    ],
}


ENUM = "enum:open|late"


def test_value_passes_each_format() -> None:
    checked = 0
    for text in PASSING.keys() | FAILING.keys():
        fmt = parse_format(text)
        for value in PASSING[text]:
            assert value_passes(fmt, value, nullable=False), (text, value)
            checked += 1
        for value in FAILING[text]:
            assert not value_passes(fmt, value, nullable=False), (text, value)
            checked += 1
        # a null passes only when the schema property allows it
        assert value_passes(fmt, None, nullable=True), text
        assert not value_passes(fmt, None, nullable=False), text
        checked += 2
    assert {*PASSING} == {*FAILING} == {"decimal", "integer", "date", "date-time", "ref", ENUM}
    print(f"values checked: {checked}")


def _descriptor(effect: EffectKind, **extra: Any) -> CapabilityDescriptor:
    return CapabilityDescriptor.model_validate(
        {
            "contract_id": "notes.note.read.v1",
            "effect": effect,
            "input_schema_id": "q",
            "output_schema_id": "n",
            **extra,
        }
    )


def test_format_on_a_non_answer_capability_is_refused() -> None:
    formats = {"/input/count": "integer"}
    for effect in (EffectKind.READ, EffectKind.WRITE):
        with pytest.raises(ValidationError, match="answer"):
            _descriptor(effect, answer_value_formats=formats)
        # no formats is the default, and admits every effect
        assert _descriptor(effect).answer_value_formats == {}
    answer = _descriptor(EffectKind.ANSWER, answer_value_formats=formats)
    assert answer.answer_value_formats == formats
    # keys are instance paths as data class keys are; values are formats of the closed set
    with pytest.raises(ValidationError, match="items"):
        _descriptor(EffectKind.ANSWER, answer_value_formats={"/input/refs/0": "ref"})
    with pytest.raises(ValidationError, match="instance path"):
        _descriptor(EffectKind.ANSWER, answer_value_formats={"/count": "integer"})
    with pytest.raises(ValidationError, match="value format"):
        _descriptor(EffectKind.ANSWER, answer_value_formats={"/input/count": "number"})


def test_admitted_value_formats_are_immutable() -> None:
    """Review A1-1: the descriptor holds a frozen copy, as admission keeps ``data_classes``;
    a change to the declaring mapping, in place or by a new key, never reaches it."""
    declared = {"/input/count": "integer"}
    answer = _descriptor(EffectKind.ANSWER, answer_value_formats=declared)
    formats = answer.answer_value_formats
    with pytest.raises(TypeError):
        formats["/input/count"] = "decimal"  # type: ignore[index]
    with pytest.raises(TypeError):
        formats["/input/extra"] = "ref"  # type: ignore[index]
    declared["/input/count"] = "decimal"
    assert dict(formats) == {"/input/count": "integer"}
    with pytest.raises(TypeError):
        _descriptor(EffectKind.ANSWER).answer_value_formats["/input/x"] = "ref"  # type: ignore[index]
    # the frozen mapping still serialises, and a dump validates back to an equal descriptor
    dumped = answer.model_dump()
    assert dumped["answer_value_formats"] == {"/input/count": "integer"}
    assert (
        json.loads(answer.model_dump_json())["answer_value_formats"]
        == dumped["answer_value_formats"]
    )
    assert CapabilityDescriptor.model_validate(dumped) == answer
    assert CapabilityDescriptor.model_validate_json(answer.model_dump_json()) == answer
    # a deep copy (pydantic deep-copies defaults) keeps the frozen mapping
    assert copy.deepcopy(answer) == answer
    assert answer.model_copy(deep=True).answer_value_formats is formats
    # the inner store is read-only too, and a pickle round trip stays frozen (review R2-1, R2-4)
    with pytest.raises(TypeError):
        formats._formats["/input/extra"] = "ref"  # type: ignore[attr-defined, index]
    restored = pickle.loads(pickle.dumps(answer))
    assert restored == answer
    with pytest.raises(TypeError):
        restored.answer_value_formats["/input/x"] = "ref"  # type: ignore[index]
