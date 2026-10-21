"""The ERP pack's answer value formats (ADR 0023 §7, D17, Task 4c.4): declared in the
manifest per answer contract, admitted beside the data classes, and never model-facing."""

import json

from e_agent.contracts.capability import EffectKind
from e_agent.plugins.erp.domain.plugin import INPUT_SCHEMAS
from e_agent.server.bootstrap import tool_specs
from e_agent.server.profile import Profile

from .test_task_definitions import _fixture

FORMATS = {
    "procurement.shortage.answer.v1": {
        "/input/demand_ref": "ref",
        "/input/product_ref": "ref",
        "/input/demand_quantity": "decimal",
        "/input/available": "decimal",
        "/input/inbound": "decimal",
        "/input/shortage": "decimal",
    },
    "procurement.offer.recommend.v1": {
        "/input/demand_ref": "ref",
        "/input/product_ref": "ref",
        "/input/offer_ref": "ref",
        "/input/supplier_ref": "ref",
        "/input/unit_price": "decimal",
    },
    "sales.late-orders.answer.v1": {
        "/input/as_of": "date",
        "/input/late_order_refs/items": "ref",
    },
    "receivables.overdue-invoices.answer.v1": {
        "/input/as_of": "date",
        "/input/overdue_invoice_refs/items": "ref",
    },
}
FREE_TEXT = ("explanation", "summary", "totals")


def _admitted() -> tuple[Profile, dict[str, dict[str, str]]]:
    profile, registry = _fixture()
    answers = {
        cid: dict(cap.answer_value_formats)
        for cid, cap in registry.capabilities.items()
        if cap.effect is EffectKind.ANSWER
    }
    return profile, answers


def test_erp_answer_formats_are_declared() -> None:
    _, answers = _admitted()
    assert answers == FORMATS
    for contract_id, formats in answers.items():
        for path in formats:
            tokens = path.split("/")
            assert not any(t in FREE_TEXT for t in tokens), (contract_id, path)
    print(f"answer contracts checked: {len(answers)}")


def test_value_formats_never_reach_the_model() -> None:
    """The tool schemas of every ERP answer contract are the plugin's own input schemas,
    unchanged, so the model sees no format (D17)."""
    profile, registry = _fixture()
    specs = {s.contract_id: s for s in tool_specs(registry, profile)}
    checked = 0
    for contract_id in FORMATS:
        cap = registry.descriptor(contract_id)
        assert cap.answer_value_formats, contract_id
        parameters = specs[contract_id].parameters
        assert parameters == INPUT_SCHEMAS[cap.input_schema_id], contract_id
        text = json.dumps(parameters)
        assert "answer_value_formats" not in text and '"ref"' not in text, contract_id
        checked += 1
    assert checked == len(FORMATS) == 4
    print(f"answer tool schemas checked: {checked}")
