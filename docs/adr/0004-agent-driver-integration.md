# ADR 0004: Pydantic AI 2.x driver — deferred-only writes and continuation hygiene

Date: 2026-10-06. Status: Proposed. Refines ADR 0001 (Pydantic AI + Ollama selected).

## Context

- Pydantic AI v2.0.0 was released on 2026-06-23. V1 receives security fixes for at least 6 months after that. Some v1-style wrappers (for example `DBOSAgent`) are deprecated toward v3.
- Pydantic AI has two human-in-the-loop mechanisms. `requires_approval` / `ApprovalRequired`: the framework executes the tool body after approval arrives in `DeferredToolResults.approvals`. `CallDeferred`: execution happens outside the framework and the result arrives in `DeferredToolResults.calls`. A run that ends with pending calls returns `DeferredToolRequests`, and the caller resumes with `message_history` plus `deferred_tool_results`.
- Message history (`ModelMessagesTypeAdapter`) is the natural continuation. With reasoning models it includes `ThinkingPart`s. Qwen3-family models served by Ollama think by default. AGENTS.md forbids persisting hidden chain-of-thought.
- Pydantic AI also offers UI adapters (ADR 0007) and durability capabilities (ADR 0003). This ADR keeps both out of the write path.

## Decision

1. Target **Pydantic AI 2.x**, pinned to an exact version in the lockfile. The driver adapter is the only package that imports `pydantic_ai`.
2. **Read tools** are ordinary tools. Their implementation calls the kernel gateway through injected `deps`, so authorization, recording and redaction happen in the host and never inside the tool.
3. **Every effectful tool raises `CallDeferred`.** The kernel maps `tool_call_id` to proposal and action IDs, then validates, requests approval, dispatches and verifies. When it resumes the driver, it passes a sanitized receipt or a typed refusal via `DeferredToolResults.calls`. `requires_approval` and `DeferredToolResults.approvals` are **not** used for business actions, because a framework-side approval is not a kernel approval.
4. **Continuation hygiene.** Default to thinking disabled for the selected model. If thinking is enabled for quality, strip `ThinkingPart`s (and any provider reasoning fields) before persisting the continuation, building evidence, emitting events or exporting traces. Persist continuation with a `driver_version` + `pydantic_ai_version` + `model_digest` envelope.
5. Tool schemas are static for a run (no mid-run tool set changes) and are generated from domain DTOs.
6. CI uses `TestModel` / `FunctionModel` and recorded-response replays, and sets the global "no real model requests" guard. Live Ollama runs only in local gates.

## Alternatives considered

- **Framework approval (`requires_approval`).** Rejected for writes: the framework would execute the effect, so the kernel would not own dispatch.
- **Own minimal agent loop on the Ollama API.** Viable and recommended by thin-framework advocates. It is kept as the fallback if Pydantic AI fails I04, and the AgentDriver port makes this a bounded change.
- **Persist thinking encrypted.** Still a store of reasoning content with retention and export risk, and there is no requirement for it.

## Consequences

- One driver package, with a narrow mapping between `DeferredToolRequests` and kernel actions.
- Thinking stripping must be re-verified when the Pydantic AI version or model changes.

## Verification

- Conformance: a deferred write never executes in-process; the fake executor records zero calls until kernel dispatch.
- Hygiene: a run with a thinking-enabled model leaves no thinking content in `runs`, `proposals`, `evidence`, `run_events`, logs or exported traces (grep plus schema assertions).
- Resume: a crash between `DeferredToolRequests` and resume recovers from the persisted continuation, or else falls back to the ledger with the run marked as needing a new driver turn.
- Revisit on a Pydantic AI major release or a failed I04 qualification.
