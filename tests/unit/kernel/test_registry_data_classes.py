"""The registry resolves data classes and counts unmarked properties (ADR 0030, Task 3b.3).

Uses the notes pack's classed read (``CLASSED_READ``, ``NOTE_OUTPUT``), never ERP.
"""

from typing import Any

import pytest
from e_agent.contracts.capability import CapabilityDescriptor
from e_agent.contracts.data_classes import DataClass
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.registry import PluginRegistry
from e_agent.sdk.ports import PluginContribution

from .conftest import BINDINGS, CLASSED_READ, CREATE, NOTE_INPUT, NOTE_OUTPUT


def _register(
    read: CapabilityDescriptor = CLASSED_READ,
    *,
    output_schemas: dict[str, Any] | None = None,
    input_schemas: dict[str, Any] | None = None,
) -> PluginRegistry:
    reg = PluginRegistry({"notes-mem.read": ("c1",)})
    reg.register(
        plugin_id="notes-fixture",
        plugin_version="1",
        declared_capabilities=(read, CREATE),
        binding_templates=BINDINGS,
        contribution=PluginContribution(
            capabilities=(read, CREATE),
            input_schemas=input_schemas if input_schemas is not None else {"c": NOTE_INPUT},
            output_schemas=(output_schemas if output_schemas is not None else {"n": NOTE_OUTPUT}),
        ),
    )
    return reg


def test_unmarked_property_counts_as_personal() -> None:
    reg = _register()
    rid = CLASSED_READ.contract_id
    assert reg.data_class(rid, "/output/properties/topic") is DataClass.INTERNAL
    assert reg.data_class(rid, "/output/properties/notes/items/properties/key") is (
        DataClass.INTERNAL
    )
    # the note text is left unmarked in the notes pack: it counts as personal
    assert reg.data_class(rid, "/output/properties/notes/items/properties/text") is (
        DataClass.PERSONAL
    )
    assert reg.data_class(CREATE.contract_id, "/input/properties/text") is DataClass.PERSONAL
    with pytest.raises(KernelError) as err:
        reg.data_class("notes.note.purge.v1", "/input/properties/text")
    assert err.value.code is ErrorCode.INVALID_REQUEST


def test_registry_counts_unmarked_properties_per_capability() -> None:
    counts = _register().unmarked_properties()
    print(f"capabilities counted: {len(counts)}")
    # the read registers no input schema and the create no output schema: None, not 0
    assert counts == {
        CLASSED_READ.contract_id: {"input": None, "output": 1},
        CREATE.contract_id: {"input": 2, "output": None},
    }


@pytest.mark.parametrize(
    "pointer",
    [
        "/output/properties/missing",
        "/output/properties/notes/items/properties/missing",
        "/output/properties/topic/properties/inner",
        "/input/properties/text",  # the read registers no input schema
    ],
)
def test_data_class_pointer_must_exist_in_schema(pointer: str) -> None:
    bad = CLASSED_READ.model_validate(
        {**CLASSED_READ.model_dump(), "data_classes": {pointer: "internal"}}
    )
    with pytest.raises(KernelError) as err:
        _register(bad)
    assert err.value.code is ErrorCode.STARTUP_REJECTED
    assert "names no property schema" in str(err.value)


def test_a_pointer_into_an_unregistered_output_schema_fails_admission() -> None:
    with pytest.raises(KernelError, match="names no property schema"):
        _register(output_schemas={})


def test_output_schemas_conflict_fails_closed() -> None:
    reg = _register()
    with pytest.raises(KernelError, match="conflicting schema definitions for n"):
        reg.register(
            plugin_id="other",
            plugin_version="1",
            declared_capabilities=(),
            binding_templates=(),
            contribution=PluginContribution(output_schemas={"n": {"type": "object"}}),
        )


def test_classes_leave_the_surface_digest_unchanged() -> None:
    """Classes sit beside the schema: the digest a run is pinned to does not move."""
    from .conftest import READ

    classed = _register().surface_digest()
    plain = _register(READ, output_schemas={}).surface_digest()
    assert classed == plain
