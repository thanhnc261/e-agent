# ADR 0001: local-first MVP with streaming UI and broader ERP tasks

Date: 2026-10-06. Status: user-selected scope; detailed task catalog and unresolved deployment choices remain proposed.

## Context

The original design limited the MVP to one procurement workflow and deferred UI. The user subsequently selected the current machine, Ollama first, Pydantic AI, the existing independent `odoo19-learning` Odoo 19 environment, permission to customize it, 5–10 common Odoo tasks, ERP Bench as a possible ontology input, a streaming overlay UI, live ERP plus BigQuery, and simple CI with predominantly local testing. Deadline and budget are not yet set.

## Decision

- Keep independent packages and the domain-neutral kernel. Procurement remains the first vertical slice, not the entire MVP.
- Select Pydantic AI with Ollama as the initial driver/provider. Qualify exact versions/model through local tool-call, structured output, deferred execution and streaming tests. Do not silently fall back to a cloud model.
- Target only the declared `odoo19-learning` stack. Existing experiment/benchmark services are not development targets.
- Include an Odoo bridge addon for narrowly scoped, idempotent business commands if the Odoo transaction spike validates it. The user permits customization; this ADR does not claim any addon has been installed.
- Include a streaming overlay frontend in the MVP. Reuse the backend API for a small CLI. The exact overlay placement is pending user clarification; frontend/server event contracts can be planned independently.
- Include a separate BigQuery adapter. The proposed initial surface is parameterized, read-only analytics; actual project, dataset, location, intended role and cloud-data permission need clarification before connection or data upload.
- Build an ontology from traceable public benchmark/domain specifications and Odoo 19 semantics, not benchmark answers. Confirm the exact ERP Bench repository/revision before adoption.
- Run deterministic tests/build checks in CI; live Ollama/Odoo/BigQuery and browser acceptance primarily run locally.

## Alternatives and consequences

The CLI-only, single-task demo is superseded because it no longer meets the requested scope. A full generic enterprise workflow engine, arbitrary SQL agent and autonomous accounting execution remain out of scope.

The expanded scope adds frontend event transport, Odoo addon packaging, analytics contracts and broader evaluation. No schedule from the earlier narrow MVP is carried forward. Implement in gated slices and measure local inference before setting latency or completion promises.

## Follow-up decisions

The [2026-10-06 architecture review](../reviews/2026-10-06-architecture-review.md) refines this ADR's technology selections in proposed ADRs 0002–0010 (see [index](README.md)). The HLD and MVP design were updated to reference this ADR's scope.

## Verification

Use the [implementation plan](../implementation-plan.md), including per-task outcome checks, durable versus transient stream behavior, duplicate-command handling, connection isolation and independent artifact tests. Complete the outstanding overlay/BigQuery/benchmark decisions before their dependent integrations; work on contracts, safety and local driver qualification can proceed independently.
