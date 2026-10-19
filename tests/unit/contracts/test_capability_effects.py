import pytest
from e_agent.contracts.capability import (
    CapabilityBinding,
    CapabilityDescriptor,
    EffectKind,
    Idempotency,
    Reversibility,
    Risk,
)
from e_agent.sdk.manifest import BindingTemplate, PluginManifest
from pydantic import ValidationError


def _capability(effect: EffectKind, **declared: object) -> CapabilityDescriptor:
    return CapabilityDescriptor.model_validate(
        {
            "contract_id": "erp.purchase.create.v1",
            "effect": effect,
            "input_schema_id": "in",
            "output_schema_id": "out",
            **declared,
        }
    )


def test_read_risk_only_on_read_or_answer_effects() -> None:
    assert _capability(EffectKind.READ, risk="read").risk is Risk.READ
    assert _capability(EffectKind.ANSWER, risk="read").risk is Risk.READ
    with pytest.raises(ValidationError, match="risk 'read'"):
        _capability(EffectKind.WRITE, risk="read")
    for risk in ("write_low", "write_high", "destructive"):
        assert _capability(EffectKind.WRITE, risk=risk).risk == risk


def test_effect_declaration_defaults() -> None:
    write = _capability(EffectKind.WRITE)
    assert write.risk is Risk.WRITE_HIGH
    assert write.reversibility is Reversibility.IRREVERSIBLE
    assert write.compensating_contract_id is None
    assert _capability(EffectKind.READ).risk is Risk.READ
    assert _capability(EffectKind.ANSWER).risk is Risk.READ
    binding = CapabilityBinding(
        binding_id="b1",
        contract_id="erp.purchase.create.v1",
        plugin_id="p",
        plugin_version="1",
        connection_id="c1",
    )
    assert binding.idempotency is Idempotency.NONE
    template = BindingTemplate(binding_id="b1", contract_id="erp.purchase.create.v1")
    assert template.idempotency is Idempotency.NONE


def test_defaulted_declarations_are_detectable() -> None:
    """Task 2c.2 refuses defaulted write declarations in live profiles: a default must show."""
    defaulted = _capability(EffectKind.WRITE)
    assert {"risk", "reversibility"}.isdisjoint(defaulted.model_fields_set)
    declared = _capability(EffectKind.WRITE, risk="write_low", reversibility="irreversible")
    assert {"risk", "reversibility"} <= declared.model_fields_set
    template = BindingTemplate(binding_id="b1", contract_id="erp.purchase.create.v1")
    assert "idempotency" not in template.model_fields_set
    keyed = BindingTemplate(
        binding_id="b1", contract_id="erp.purchase.create.v1", idempotency="provider_key"
    )
    assert keyed.idempotency is Idempotency.PROVIDER_KEY
    assert "idempotency" in keyed.model_fields_set


def test_existing_manifest_shape_still_loads() -> None:
    manifest = PluginManifest.model_validate(
        {
            "plugin_id": "p",
            "version": "1",
            "sdk_api": ">=1.0,<2.0",
            "factory": "m:f",
            "kind": "domain",
            "provides_capabilities": [
                {
                    "contract_id": "erp.purchase.create.v1",
                    "effect": "write",
                    "input_schema_id": "in",
                    "output_schema_id": "out",
                }
            ],
            "provides_bindings": [{"binding_id": "b1", "contract_id": "erp.purchase.create.v1"}],
        }
    )
    capability = manifest.provides_capabilities[0]
    assert capability.risk is Risk.WRITE_HIGH
    assert "risk" not in capability.model_fields_set
    assert manifest.provides_bindings[0].idempotency is Idempotency.NONE


def test_compensable_names_its_compensating_contract() -> None:
    compensable = _capability(
        EffectKind.WRITE,
        risk="write_low",
        reversibility="compensable",
        compensating_contract_id="erp.purchase.cancel.v1",
    )
    assert compensable.reversibility is Reversibility.COMPENSABLE
    with pytest.raises(ValidationError, match="compensating_contract_id"):
        _capability(EffectKind.WRITE, reversibility="compensable")
    with pytest.raises(ValidationError, match="compensating_contract_id"):
        _capability(EffectKind.WRITE, compensating_contract_id="erp.purchase.cancel.v1")
    with pytest.raises(ValidationError, match="contract id"):
        _capability(
            EffectKind.WRITE, reversibility="compensable", compensating_contract_id="cancel"
        )
