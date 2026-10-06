# ADR 0010: evaluation protocol — pass@1 in development, pass^k at release

Date: 2026-10-06. Status: Accepted (project owner, decisions D1–D5, 2026-10-06).

## Context

The plan requires "three verifier-passing live trials per claimed task". In other words, it requires pass^3 = 1 per task. The plan defines neither the metric nor the trial protocol. τ-bench introduced pass^k (the probability that all k i.i.d. trials succeed) because single-trial success hides inconsistency; for example, 0.60 pass@1 fell to 0.38 pass^4. Local models served through Ollama add variance from quantization, context settings and cold or warm load.

## Decision

1. **Trial protocol.** Each trial records the model digest, Ollama version, context and sampling parameters, Pydantic AI version, profile, scenario seed, fixture snapshot ID, and cold or warm state. Trials of one task run on a freshly reset sandbox namespace. Temperature and other sampling settings are fixed per release candidate.
2. **Development metric.** pass@1 is estimated over N ≥ 10 trials per task, with failures classified as model, driver, adapter, environment or verifier.
3. **Release gate per claimed task.** All deterministic safety gates pass, and pass^3 = 1 on three *consecutive* trials of the frozen release candidate. A failure resets the count. Every failed trial is kept in the report.
4. **Safety metrics are not sampled.** Any unsafe outcome is a release blocker regardless of pass^k: a dispatch without matching approval, a duplicate external effect, or a cross-scope read.
5. **Regression.** Recorded model responses (`FunctionModel` replay) of passing trials become deterministic CI regressions. They are labelled as replays, not live evidence.
6. **I04 rescope checkpoint.** If no local model reaches pass@1 ≥ 0.8 on the deferred-write qualification scenario, stop adding tasks. Tune the tool surface and model settings, or propose a scope change.

## Alternatives considered

- **Best-of-k showcase.** Rejected; AGENTS.md forbids cherry-picking.
- **Large statistical sample per task.** Desirable later; it is infeasible on local hardware for the MVP and is not claimed.

## Consequences

- Reports state pass@1 with N, and pass^3 for released tasks. They make no reliability claims beyond those numbers.

## Verification

- The report generator refuses to mark a task released without the recorded metadata and an unbroken pass^3 sequence.
