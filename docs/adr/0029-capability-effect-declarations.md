# ADR 0029: Capability effect declarations: risk, reversibility, idempotency

Date: 2026-10-14. Status: Accepted (owner, 2026-10-18, gate G1 of the Phase 2 plan). Refines ADRs 0002, 0003, 0005; MVP design §9; [target architecture](../design/target-architecture.md) §6.4.2.

## Context

`CapabilityDescriptor.effect` is `read | write | answer` (the `EffectKind` enum in `contracts/capability.py`). Nothing records:
- how severe a write is;
- whether it can be undone;
- whether its provider deduplicates a repeated call.

AGENTS.md ("never blindly replay a possibly committed write") and MVP §9 ("do not assume standard RPC create is idempotent") state rules that depend on these facts, but nothing declares them. The Odoo bridge enforces an `operation_key` (`OdooExecutor.execute` in `plugins/erp/odoo/executor.py` sends `operation_key=action.logical_operation_id`), and no contract says so.

Several changes need these facts:
- Phase 2 multi-write plans need them for retry, reconciliation and approval presentation.
- ADR 0024 needs them to limit benchmark auto-approve.
- Phase 8 MCP needs a safe default for unmapped tools.

The [adoption review](../reviews/2026-10-14-x-agent-adoption-review.md) XA-01, approved by the owner on 2026-10-14, adopts this.

## Decision

- Capability contracts declare `risk` (`read`, `write_low`, `write_high`, `destructive`) and `reversibility` (`irreversible`, or `compensable` naming the compensating contract). Bindings declare `idempotency` (`none`, `provider_key`) on `CapabilityBinding` (`contracts/capability.py`), set through the manifest's `BindingTemplate` (`sdk/manifest.py`). Fields and defaults are as in target §6.4.2.
- `risk: read` only with `effect: read | answer`; a write never declares `read`.
- Defaults keep existing manifests loadable: `write_high`, `irreversible`, `none` for writes; `read` for reads and answers. A profile with `environment: live` refuses a write capability or write binding that relies on a default. Fixture profiles accept and report defaults.
- The declarations are not approval-digest inputs. They come from admitted, digest-pinned artifacts and cannot change during a run.
- The approval presentation shows a plan's highest risk and its irreversible steps, as a presentation annotation under ADR 0015 (not a digest input; the T9 card check is unchanged).
- Unmapped tools (MCP, Phase 8) are `write_high`, `irreversible`, `none`. A provider's hints never set these values.
- An ambiguous write still goes to reconciliation (ENG-TRUST-5). A re-send is allowed only for a binding that declares `provider_key` **and** passes a conformance test proving the deduplication. Phase 2 implements the declarations and the live refusal, and leaves re-sending off.
- The notes fixture domain declares the fields.

## Alternatives considered

- Idempotency on the capability contract: rejected because deduplication is a provider property. Two bindings of one contract can differ.
- Risk as an approval-digest input: rejected because the declarations come from digest-pinned artifacts and `rule_bundle_version` already binds pack changes. Adding them would change every existing digest.
- Required fields with no defaults: rejected for Phase 2 because every manifest would fail at once. The live refusal gives the same safety where it matters.

## Consequences

- Code: `CapabilityDescriptor` gains `risk` and `reversibility`, `CapabilityBinding` and `BindingTemplate` gain `idempotency`; registry validation and the live refusal; approval presentation; the ERP pack and the Odoo manifest declare them.
- Tests and evidence: contract validation (read risk only on reads); live profile refuses a defaulted write; fixture profile reports defaults; presentation shows the highest risk; notes-domain declarations. Plugin digests are re-pinned.
- Operations: release evidence lists any defaulted declarations.

## Gates

Phase 2 Tasks 2c.1 and 2c.2 (fields and declarations, including the live refusal at registry admission), 2c.7 (presentation) and 2c.8 (reconciliation rule), gate `full`, plus `pg` for 2c.1, 2c.7 and 2c.8.
