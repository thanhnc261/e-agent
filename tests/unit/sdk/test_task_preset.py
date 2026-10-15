"""TaskPreset renders its prompt by replacing default refs in turn (R-3)."""

from __future__ import annotations

import pytest
from e_agent.sdk.ports import TaskPreset

PRESET = TaskPreset(
    kind="quote",
    prompt="Quote customer:acme for product:a.",
    default_refs={"customer_ref": "customer:acme", "product_ref": "product:a"},
)


def test_render_replaces_defaults_in_turn() -> None:
    assert PRESET.render() == "Quote customer:acme for product:a."
    assert PRESET.render([("product_ref", "product:b"), ("unknown", "x")]) == (
        "Quote customer:acme for product:b."
    )
    # An override equal to another default is replaced again by a later override.
    assert PRESET.render([("customer_ref", "product:a"), ("product_ref", "product:b")]) == (
        "Quote product:b for product:b."
    )
    # A name may come twice; each replacement applies to the text so far.
    assert PRESET.render([("product_ref", "product:a"), ("product_ref", "product:c")]) == (
        "Quote customer:acme for product:c."
    )


def test_empty_default_refused() -> None:
    with pytest.raises(ValueError, match="customer_ref"):
        TaskPreset(kind="quote", prompt="Quote.", default_refs={"customer_ref": ""})


def test_equality_includes_default_ref_order() -> None:
    reordered = TaskPreset(
        kind="quote",
        prompt=PRESET.prompt,
        default_refs={"product_ref": "product:a", "customer_ref": "customer:acme"},
    )
    assert reordered != PRESET
    assert TaskPreset(PRESET.kind, PRESET.prompt, dict(PRESET.default_refs)) == PRESET
