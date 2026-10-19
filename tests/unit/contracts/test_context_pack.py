import pytest
from e_agent.contracts.context_pack import (
    ClassAction,
    ContextLayer,
    ContextPack,
    ContextPolicy,
    ContextRoute,
    Dropped,
    RenderedObservation,
)
from e_agent.contracts.data_classes import DataClass
from e_agent.contracts.evidence import Completeness, EvidenceRef
from pydantic import ValidationError

NOW = "2026-10-19T00:00:00Z"


def _ref(completeness: Completeness = Completeness.COMPLETE) -> EvidenceRef:
    return EvidenceRef(
        evidence_id="ev1",
        tenant_id="t",
        source="s",
        locator="l",
        revision=None,
        observed_at=NOW,
        scope="sc",
        completeness=completeness,
    )


def _pack(**kw: object) -> ContextPack:
    base: dict[str, object] = {
        "stable_prefix": {ContextLayer.INSTRUCTIONS: "be careful"},
        "dynamic_suffix": {ContextLayer.LEDGER: "step 1"},
        "observations": (RenderedObservation(evidence=_ref(), data={"n": 3}, partial=False),),
    }
    base.update(kw)
    return ContextPack.build(**base)  # type: ignore[arg-type]


def test_pack_digest_is_stable() -> None:
    a, b = _pack(), _pack()
    assert a.digest == b.digest and a.digest.startswith("jcs-sha256-v1:")
    assert _pack(dynamic_suffix={ContextLayer.LEDGER: "step 2"}).digest != a.digest
    with pytest.raises(ValidationError):
        ContextPack(**{**a.model_dump(), "digest": "jcs-sha256-v1:" + "0" * 64})


def test_pack_rejects_unknown_layer() -> None:
    with pytest.raises(ValueError, match="holds only"):
        _pack(stable_prefix={"memory": "x"})
    with pytest.raises(ValueError, match="holds only"):
        _pack(stable_prefix={ContextLayer.LEDGER: "dynamic layer in the prefix"})
    with pytest.raises(ValueError, match="holds only"):
        _pack(dynamic_suffix={ContextLayer.TASK: "stable layer in the suffix"})


def test_dropped_requires_reason() -> None:
    with pytest.raises(ValidationError):
        Dropped(kind="value", ref="ev1#/a")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Dropped(kind="value", ref="ev1#/a", reason="because")  # type: ignore[arg-type]
    assert Dropped(kind="value", ref="ev1#/a", reason="class_route").reason == "class_route"


@pytest.mark.parametrize(
    ("completeness", "truncated", "masked", "partial", "ok"),
    [
        (Completeness.COMPLETE, False, False, False, True),
        (Completeness.COMPLETE, False, False, True, False),
        (Completeness.COMPLETE, True, False, False, False),
        (Completeness.COMPLETE, True, False, True, True),
        (Completeness.COMPLETE, False, True, True, True),
        (Completeness.COMPLETE, False, True, False, False),
        (Completeness.PARTIAL, False, False, True, True),
        (Completeness.PARTIAL, False, False, False, False),
        (Completeness.UNKNOWN, False, False, True, True),
    ],
)
def test_rendered_observation_partial_requires_marker(
    completeness: Completeness, truncated: bool, masked: bool, partial: bool, ok: bool
) -> None:
    def build() -> RenderedObservation:
        return RenderedObservation(
            evidence=_ref(completeness),
            data={},
            partial=partial,
            truncated=truncated,
            masked=masked,
        )

    if ok:
        build()
    else:
        with pytest.raises(ValidationError):
            build()


def test_policy_defaults_follow_the_class_route_table() -> None:
    rules = ContextPolicy().class_rules
    assert rules[ContextRoute.LOCAL][DataClass.SENSITIVE_PERSONAL] is ClassAction.KEEP
    assert rules[ContextRoute.HOSTED_DECLARED][DataClass.PERSONAL] is ClassAction.KEEP
    assert rules[ContextRoute.HOSTED_DECLARED][DataClass.SENSITIVE_PERSONAL] is ClassAction.MASK
    assert rules[ContextRoute.HOSTED_UNDECLARED][DataClass.PERSONAL] is ClassAction.MASK
    for route in ContextRoute:
        assert rules[route][DataClass.SECRET] is ClassAction.ABSENT
        assert rules[route][DataClass.INTERNAL] is ClassAction.KEEP


def test_policy_refuses_a_secret_that_may_be_present() -> None:
    rules = {r: dict(v) for r, v in ContextPolicy().class_rules.items()}
    rules[ContextRoute.LOCAL][DataClass.SECRET] = ClassAction.KEEP
    with pytest.raises(ValidationError):
        ContextPolicy(class_rules=rules)
