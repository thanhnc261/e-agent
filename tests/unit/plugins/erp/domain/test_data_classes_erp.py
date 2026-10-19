"""The ERP pack's data classes (ADR 0030, Task 3b.3): declared beside the schemas, every
pointer resolves at admission, and every read output property is classed."""

from e_agent.contracts.capability import EffectKind
from e_agent.contracts.data_classes import ClassIndex, DataClass, leaf_property_pointers
from e_agent.kernel.registry import PluginRegistry
from e_agent.plugins.erp.domain.plugin import INPUT_SCHEMAS, create_plugin, load_manifest
from e_agent.sdk.ports import PluginServices

PARTNER_NAMES = {
    "crm.contact.read.v1": "/output/properties/name",
    "sales.pricing.read.v1": "/output/properties/customer_name",
    "crm.lead.read.v1": "/output/properties/leads/items/properties/name",
}
INTERNAL = {
    "procurement.demand.read.v1": (
        "/output/properties/quantity",
        "/output/properties/budget",
        "/output/properties/demand_ref",
        "/output/properties/product_ref",
    ),
    "inventory.availability.read.v1": (
        "/output/properties/available",
        "/output/properties/inbound",
        "/output/properties/product_ref",
    ),
    "procurement.offers.read.v1": (
        "/output/properties/offers/items/properties/offer_ref",
        "/output/properties/offers/items/properties/supplier_ref",
        "/output/properties/offers/items/properties/unit_price",
    ),
    "procurement.open-demands.read.v1": (
        "/output/properties/demands/items/properties/quantity",
        "/output/properties/demands/items/properties/demand_ref",
    ),
    "sales.open-orders.read.v1": ("/output/properties/orders/items/properties/customer_ref",),
    "receivables.open-invoices.read.v1": (
        "/output/properties/invoices/items/properties/residual",
        "/output/properties/invoices/items/properties/invoice_ref",
    ),
}


def _registry() -> PluginRegistry:
    """The ERP pack registered alone: admission resolves every declared pointer."""
    manifest = load_manifest()
    reg = PluginRegistry({})
    reg.register(
        plugin_id=manifest.plugin_id,
        plugin_version=manifest.version,
        declared_capabilities=manifest.provides_capabilities,
        binding_templates=manifest.provides_bindings,
        declared_task_definitions=manifest.provides_task_definitions,
        contribution=create_plugin(PluginServices(settings={})),
    )
    return reg


def test_erp_read_outputs_are_marked() -> None:
    reg = _registry()
    reads = [c for c in reg.capabilities.values() if c.effect is EffectKind.READ]
    checked = 0
    for cap in reads:
        document = reg.schema_document(cap.contract_id)
        assert "output" in document, f"{cap.contract_id}: no output schema registered"
        outputs = [p for p in leaf_property_pointers(document) if p.startswith("/output/")]
        assert outputs, cap.contract_id
        index = ClassIndex(document, cap.data_classes)
        unclassed = [p for p in outputs if index.declared(p) is None]
        assert not unclassed, (cap.contract_id, unclassed)
        checked += len(outputs)
    print(f"ERP read capabilities: {len(reads)}, output properties classed: {checked}")
    assert len(reads) == 13 and checked > 0

    for contract_id, pointer in PARTNER_NAMES.items():
        assert reg.data_class(contract_id, pointer) is DataClass.PERSONAL, contract_id
    for contract_id, pointers in INTERNAL.items():
        for pointer in pointers:
            assert reg.data_class(contract_id, pointer) is DataClass.INTERNAL, pointer


def test_every_email_or_partner_name_property_is_personal() -> None:
    """No ERP schema has an email property today; one that appears must be personal."""
    reg = _registry()
    seen = 0
    for cid in reg.capabilities:
        for pointer in leaf_property_pointers(reg.schema_document(cid)):
            leaf = pointer.rsplit("/", 1)[-1]
            if "email" in leaf or leaf in {"customer_name", "contact_name", "partner_name"}:
                assert reg.data_class(cid, pointer) is DataClass.PERSONAL, (cid, pointer)
                seen += 1
    print(f"email and partner-name properties: {seen}")
    assert seen >= 1


def test_erp_unmarked_counts() -> None:
    """Every registered ERP property is classed. Write and answer outputs are host records
    (receipts, verified answers) with no plugin output schema: their output side is None,
    which readiness shows apart from a fully classed 0."""
    reg = _registry()
    counts = reg.unmarked_properties()
    print(f"ERP capabilities counted: {len(counts)}")
    assert len(counts) == 21
    for cid, sides in counts.items():
        assert sides["input"] == 0, cid
        has_output = reg.capabilities[cid].effect is EffectKind.READ
        assert sides["output"] == (0 if has_output else None), cid


def test_classes_leave_the_model_facing_input_schemas_alone() -> None:
    reg = _registry()
    assert reg.input_schemas == INPUT_SCHEMAS
    for schema in INPUT_SCHEMAS.values():
        assert "data_classes" not in str(schema) and "x-data-class" not in str(schema)
