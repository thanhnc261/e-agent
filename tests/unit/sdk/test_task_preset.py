"""TaskPreset renders its prompt from default refs and profile overrides (R-3)."""

from __future__ import annotations

import pytest
from e_agent.sdk.ports import TaskPreset

PRESET = TaskPreset(
    kind="restock",
    prompt="Restock {product_ref} for {demand_ref}.",
    default_refs={"product_ref": "product:a", "demand_ref": "demand:1"},
)


def test_render_uses_defaults_then_overrides() -> None:
    assert PRESET.render() == "Restock product:a for demand:1."
    assert PRESET.render({"product_ref": "product:b", "unused": "x"}) == (
        "Restock product:b for demand:1."
    )


def test_placeholder_without_default_refused() -> None:
    with pytest.raises(ValueError, match="customer_ref"):
        TaskPreset(kind="quote", prompt="Quote for {customer_ref}.")


def test_positional_placeholder_refused() -> None:
    with pytest.raises(ValueError, match="named"):
        TaskPreset(kind="quote", prompt="Quote for {}.")
