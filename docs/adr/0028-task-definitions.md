# ADR 0028: Task definitions with acceptance specs as domain-pack resources

Date: 2026-10-14. Status: Proposed. Refines ADRs 0017, 0019; [target architecture](../design/target-architecture.md) §1.3, §6.4.1, §7.2 rule 1, §17 C11.

## Context

Today every run receives every agent-visible capability with one binding (`server/bootstrap.py:106-133`), about 18 tools, and many more after Phase 5. "Done" is decided only by the verifier of the last action, so a run that never produces the required effect has no typed failure (AR-01). Task identity is spread over the CLI (`TASK_PROMPTS`), the scripted fixtures (`TASK_KINDS`, `DEFAULT_REFS`) and the server's `TaskTemplate` (ADR 0017). The Phase 1d plan moves these into domain-pack "task presets". ADR 0019 deferred a per-task approval TTL until task definitions exist.

## Decision

- A `TaskDefinition` (fields in target §6.4.1) is a versioned domain-pack resource, declared in the pack manifest and admitted by the registry. The registry refuses a definition whose capability has no admitted binding, and a duplicate `task_id`.
- Phase 1d's task presets are the first version of this resource. Phase 2 extends them, and the one name is `TaskDefinition`.
- The server's `TaskTemplate` (ADR 0017) becomes a projection of an admitted task definition plus the requester's availability. Its public shape does not change in Phase 2.
- The run's tool set is fixed at admission to the definition's agent-visible capabilities, and stays fixed for the whole run (target §7.2 rule 1).
- The run records `task_id` and `version`.
- `AcceptanceSpec` (required verified effects, or a required verified answer) is checked by the kernel at run end. When it is unmet, the run fails with `ACCEPTANCE_UNMET` and an acceptance finding. Model output cannot satisfy it (ENG-TRUST-1).
- A definition's `budgets` can only narrow the profile's budgets. Its `approval_ttl` replaces the global TTL for its runs (ADR 0019 follow-up).
- A general `assistant` definition with read-only capabilities serves open questions.
- The notes fixture domain carries a task definition, so the core is tested without ERP (DR-08).

## Alternatives considered

- A task catalog in the server or the profile: rejected because tasks are domain behaviour and belong to domain packs (HLD §4, AGENTS.md "Domain logic does not belong in HTTP handlers").
- Progressive tool disclosure (a search tool that mounts capabilities on demand): deferred until a single task's capability set no longer fits the context budget (about 30–40 tools). Fixed per-task sets keep the KV cache valid and the attack surface small.
- Model-selected task type without host resolution: rejected because a model selects nothing that grants tools.

## Consequences

- Code: `contracts/task.py`; resources under the ERP pack's `tasks/`; a manifest declaration; registry admission; run-loop tool set; an acceptance check at run end; `ReasonCode.ACCEPTANCE_UNMET`.
- Tests and evidence: eight ERP definitions load, and their capability sets equal today's tool lists (golden); registry refusals; notes-domain definition; acceptance-unmet test. Plugin digests are re-pinned.
- Operations: the task catalog shows the same templates; adding a task is a pack release, not a server change.

## Gates

Phase 2 Tasks 2c.1, 2c.2 and 2c.6, gate `full`, plus `pg` for 2c.6.
