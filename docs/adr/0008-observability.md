# ADR 0008: OpenTelemetry with GenAI conventions, separate from evidence

Date: 2026-10-06. Status: Proposed.

## Context

The HLD treats telemetry as optional and separate from the durable action record, which is correct, but it names no standard. OpenTelemetry GenAI semantic conventions (model, agent, tool and MCP spans; token metrics) are the cross-vendor standard. As of mid-2026 they are still all **Development** stability, and in June 2026 they moved to a dedicated repository. Pydantic AI emits OTel spans natively and can include or exclude message content.

## Decision

1. Instrument the server, kernel and adapters with OpenTelemetry (traces, metrics, logs). Pin the GenAI semconv version via `OTEL_SEMCONV_STABILITY_OPT_IN` or the equivalent library setting, and record it in evidence.
2. **Content capture is off by default.** Prompts, completions, tool arguments and tool results are not span attributes or events. Opt-in exists for local debugging and is marked in the run's evidence.
3. Trace and span IDs are copied into `RunEvent` correlation fields, so an operator can move from the evidence bundle to traces. The reverse link (trace → evidence) uses run/action IDs only.
4. Metrics use bounded labels only: capability ID, outcome status, error code, model ID. No tenant names, record IDs or free text.
5. The exporter is OTLP to a local collector or viewer in development. A backend choice is not part of the MVP. Logfire is allowed but not required.
6. Telemetry export failure never blocks a run (mandatory evidence lives in PostgreSQL).

## Alternatives considered

- **Vendor SDK tracing only (e.g. LangSmith).** Locks telemetry to one vendor and does not cover the kernel or adapters.
- **Wait for stable semconv.** It would leave the MVP without traces; pinning a version contains the churn.

## Consequences

- Attribute names may change between semconv releases, so dashboards must be updated on upgrade.

## Verification

- Test: with default settings, exported spans contain no prompt or tool-payload content (in-memory exporter assertion).
- Test: every `RunEvent` written during a traced run carries a trace ID.
