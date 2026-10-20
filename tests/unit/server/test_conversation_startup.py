"""The ``features.conversations`` startup rule (ADR 0023 §9, Task 4c.1).

A profile with ``conversations: on`` is refused unless ``context_assembler`` is ``on``: both
modes are pinned together, so a run pinned ``conversations: on`` is pinned
``context_assembler: on`` and the per-call route check (ADR 0032 §9) covers what it sends.
``shadow`` carries no context to the driver and is allowed with any ``context_assembler``
mode. The refusal names the settings, never a mode value.
"""

from __future__ import annotations

import re

import pytest
from e_agent.contracts.features import FeatureMode, Features
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import Profile, load_profile

MODE_WORD = re.compile(r"\b(on|off|shadow)\b", re.IGNORECASE)


def _profile(features: Features) -> Profile:
    return load_profile(fixture_profile_path()).model_copy(update={"features": features})


@pytest.mark.parametrize("context_assembler", [FeatureMode.OFF, FeatureMode.SHADOW])
async def test_conversations_on_requires_context_assembler_on(
    context_assembler: FeatureMode,
) -> None:
    features = Features(conversations=FeatureMode.ON, context_assembler=context_assembler)
    with pytest.raises(KernelError) as err:
        await build_runtime(_profile(features))
    assert err.value.code is ErrorCode.STARTUP_REJECTED
    message = str(err.value)
    assert "features.conversations" in message
    assert "features.context_assembler" in message
    assert not MODE_WORD.search(message), message  # names the setting, never a value
    # With context_assembler on the same profile starts, and its runs pin both modes.
    both = Features(conversations=FeatureMode.ON, context_assembler=FeatureMode.ON)
    runtime = await build_runtime(_profile(both))
    pin = runtime.coordinator._pin_modes()
    assert pin is not None
    assert (pin.conversations, pin.context_assembler) == (FeatureMode.ON, FeatureMode.ON)


@pytest.mark.parametrize("context_assembler", list(FeatureMode))
async def test_conversations_shadow_allowed_with_any_context_assembler_mode(
    context_assembler: FeatureMode,
) -> None:
    features = Features(conversations=FeatureMode.SHADOW, context_assembler=context_assembler)
    runtime = await build_runtime(_profile(features))
    pin = runtime.coordinator._pin_modes()
    assert pin is not None
    assert (pin.conversations, pin.context_assembler) == (FeatureMode.SHADOW, context_assembler)
