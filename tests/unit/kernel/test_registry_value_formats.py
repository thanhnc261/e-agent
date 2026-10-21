"""Registry admission of answer value formats (ADR 0023 §7, D17, Task 4c.4).

Uses the notes pack's answer (``SUMMARY``) with a classed input schema registered for the
test, never ERP: the shared fixture registers no input schema for it.
"""

from collections.abc import Mapping
from typing import Any

import pytest
from e_agent.contracts.value_formats import FrozenFormats
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.registry import PluginRegistry
from e_agent.sdk.ports import PluginContribution

from .conftest import BINDINGS, CREATE, READ, SUMMARY

SUMMARY_INPUT = {
    "type": "object",
    "properties": {
        "count": {"type": "integer"},
        "topic": {"type": "string"},
        "pinned": {"type": "boolean"},
        "total": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "keys": {"type": "array", "items": {"type": "string"}},
        "untyped": {"description": "no type: no format can be checked against it"},
    },
}
CLASSES = {
    "/input/count": "internal",
    "/input/topic": "internal",
    "/input/pinned": "internal",
    "/input/total": "internal",
    "/input/keys": "internal",
    "/input/untyped": "internal",
}
ADMITTED = {
    "/input/count": "integer",
    "/input/topic": "enum:open|late",
    "/input/total": "decimal",
    "/input/keys/items": "ref",
}


def _register(formats: dict[str, str], classes: dict[str, str] | None = None) -> PluginRegistry:
    summary = SUMMARY.model_validate(
        {
            **SUMMARY.model_dump(),
            "data_classes": CLASSES if classes is None else classes,
            "answer_value_formats": formats,
        }
    )
    reg = PluginRegistry({"notes-mem.read": ("c1",)})
    reg.register(
        plugin_id="notes-fixture",
        plugin_version="1",
        declared_capabilities=(READ, CREATE, summary),
        binding_templates=BINDINGS,
        contribution=PluginContribution(
            capabilities=(READ, CREATE, summary), input_schemas={"s": SUMMARY_INPUT}
        ),
    )
    return reg


def _refused(formats: dict[str, str], classes: dict[str, str] | None = None) -> str:
    with pytest.raises(KernelError) as err:
        _register(formats, classes)
    assert err.value.code is ErrorCode.STARTUP_REJECTED
    message = str(err.value)
    assert SUMMARY.contract_id in message
    return message


def test_registry_admits_formats_and_reads_them_through_the_descriptor() -> None:
    reg = _register(ADMITTED)
    assert dict(reg.descriptor(SUMMARY.contract_id).answer_value_formats) == ADMITTED


def _register_unvalidated(formats: Mapping[str, str]) -> None:
    summary = SUMMARY.model_copy(update={"data_classes": CLASSES, "answer_value_formats": formats})
    PluginRegistry({}).register(
        plugin_id="notes-fixture",
        plugin_version="1",
        declared_capabilities=(summary,),
        binding_templates=(),
        contribution=PluginContribution(
            capabilities=(summary,), input_schemas={"s": SUMMARY_INPUT}
        ),
    )


def test_registry_refuses_an_unknown_format() -> None:
    """The descriptor validator refuses one too; a copy that skipped validation does not
    get past admission."""
    with pytest.raises(KernelError, match="unknown answer value format"):
        _register_unvalidated(FrozenFormats({"/input/count": "number"}))


def test_registry_refuses_formats_that_are_not_frozen() -> None:
    """Review A1-1: a copy that skipped validation keeps a mutable mapping, which a plugin
    could change after admission; admission refuses it."""
    with pytest.raises(KernelError, match="not frozen"):
        _register_unvalidated({"/input/count": "integer"})
    _register_unvalidated(FrozenFormats({"/input/count": "integer"}))


def test_registry_refuses_a_format_path_the_schema_lacks() -> None:
    cases: list[dict[str, str]] = [
        {"/input/absent": "ref"},
        {"/input/count/items": "integer"},
        {"/input/topic/inner": "ref"},
        {"/output/count": "integer"},  # a format is on the answer's input only
    ]
    for formats in cases:
        message = _refused(formats)
        assert next(iter(formats)) in message and "input schema" in message, formats
    print(f"absent paths refused: {len(cases)}")


def test_registry_refuses_a_format_the_schema_type_cannot_hold() -> None:
    cases: list[dict[str, str]] = [
        {"/input/topic": "integer"},  # integer on a string property
        {"/input/pinned": "decimal"},  # decimal on a boolean
        {"/input/count": "decimal"},
        {"/input/count": "ref"},
        {"/input/keys": "ref"},  # an array is not a string
        {"/input/untyped": "ref"},
    ]
    for formats in cases:
        message = _refused(formats)
        assert next(iter(formats)) in message and "cannot hold" in message, formats
    # a nullable union is judged by its non-null member
    assert _register({"/input/total": "ref"}).descriptor(SUMMARY.contract_id)
    print(f"type mismatches refused: {len(cases)}")


def test_registry_refuses_a_format_without_a_data_class() -> None:
    classes: dict[str, Any] = {k: v for k, v in CLASSES.items() if k != "/input/count"}
    assert "data_classes" in _refused({"/input/count": "integer"}, classes)
    unclassed = {k: v for k, v in CLASSES.items() if k != "/input/keys"}
    assert "data_classes" in _refused({"/input/keys/items": "ref"}, unclassed)
    assert "data_classes" in _refused({"/input/topic": "enum:a"}, {})
    # an entry on an ancestor covers the path (ADR 0023 §7, ClassIndex.declared)
    reg = _register({"/input/keys/items": "ref"})
    formats = reg.descriptor(SUMMARY.contract_id).answer_value_formats
    assert dict(formats) == {"/input/keys/items": "ref"}
