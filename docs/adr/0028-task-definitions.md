# ADR 0028: Task definitions with acceptance specs as domain-pack resources

Date: 2026-10-14. Status: Accepted (owner, 2026-10-18, gate G1 of the Phase 2 plan). Refines ADRs 0017, 0019; [target architecture](../design/target-architecture.md) §1.3, §6.4.1, §7.2 rule 1, §17 C11.

## Context

Today every run receives every agent-visible capability with exactly one binding in scope (`tool_specs` in `server/bootstrap.py`), about 18 tools, and many more after Phase 5. The API builds one runtime, and one driver, for every task kind (`build_runtime` (`server/bootstrap.py`), called once by `server/api.py`), so a tool set fixed when the driver is built cannot differ per run. "Done" is decided only by the verifier of the last action, so a run that never produces the required effect has no typed failure (AR-01). Phase 1d moved task identity into domain-pack task presets (`TaskPreset` in `sdk/ports.py`, contributed by the ERP pack's `plugin.py`): a kind, a prompt and default refs, with no capability set, acceptance or budgets. The CLI selects a preset by kind (`--task`), but a run records only its task text, and the server's task catalog (`task_catalog` in `kernel/discovery.py`, ADR 0017) lists one `TaskTemplate` per agent-visible write or answer capability. ADR 0019 deferred a per-task approval TTL until task definitions exist.

## Decision

- A `TaskDefinition` (fields in target §6.4.1) is a versioned domain-pack resource, declared in the pack manifest and admitted by the registry. The registry refuses a definition whose capability has no admitted binding, and a duplicate `task_id`.
- Phase 1d's task presets are the first version of this resource. Phase 2 extends them, and the one name is `TaskDefinition`. A definition's `task_id` is its preset's `kind`.
- A run names its definition by `task_id` (owner decision D8, confirmed at G1). In Phase 2 only the CLI passes it: `start_run` takes an optional task kind, and the CLI passes the preset kind it renders (`--task`, or the CLI's default preset). The API's `CreateRun` carries free text only, so an API or UI run resolves no definition: with `execution_ir: shadow` it records `ir.shadow_failed` with `IR_TASK_UNRESOLVED` and nothing else, and with `on` it falls back with `IR_TASK_UNRESOLVED` (ADR 0025). The API does not use the profile's `driver.task_kind`: that is the runtime's one default kind, used to build the scripted driver, so applying it to every free-text API run would bind runs to a definition the requester never chose. The alternative, an optional task id on `CreateRun` in Phase 2, was not chosen.
- The server's `TaskTemplate` (ADR 0017) is to become a projection of an admitted task definition plus the requester's availability, together with a task id on `CreateRun`. Phase 2 keeps today's catalog and the template's public shape unchanged; the projection lands with the UI task-entry work.
- The run's tool set is fixed at admission to the definition's agent-visible capabilities, and stays fixed for the whole run (target §7.2 rule 1).
- **How the tool set reaches the driver** (owner decision D6, Phase 2 plan): the run loop sets `DriverInput.allowed_capabilities` on every turn from the admitted definition; `None` keeps today's set. The kernel refuses any read (gateway) or proposal outside the set, and that refusal is the boundary; the driver's filter only shapes what the model sees. The field is an additive SDK port change, in the same `sdk_api` minor bump as `ProposePlan` (ADR 0025).
- The run records `task_id` and `task_version` (nullable fields on `RunRecord`).
- `AcceptanceSpec` (required verified effects, or a required verified answer) is checked by the kernel at run end. When it is unmet, the run fails with `ACCEPTANCE_UNMET` and an acceptance finding. Model output cannot satisfy it (ENG-TRUST-1).
- A definition's `budgets` can only narrow the profile's budgets: admission refuses a definition whose budget is wider than the profile's. Its `approval_ttl` replaces the global TTL for its runs (ADR 0019 follow-up). Both are implemented in Phase 2 (owner decision D7): the registry refusal in Task 2c.2, and runs using the definition's TTL and narrowed budgets in Task 2c.6.
- A general `assistant` definition with read-only capabilities serves open questions.
- The notes fixture domain carries a task definition, so the core is tested without ERP (DR-08).

## Alternatives considered

- A task catalog in the server or the profile: rejected because tasks are domain behaviour and belong to domain packs (HLD §4, AGENTS.md "Domain logic does not belong in HTTP handlers").
- Progressive tool disclosure (a search tool that mounts capabilities on demand): deferred until a single task's capability set no longer fits the context budget (about 30–40 tools). Fixed per-task sets keep the KV cache valid and the attack surface small.
- Model-selected task type without host resolution: rejected because a model selects nothing that grants tools.

## Consequences

- Code: `contracts/task.py`; `RunRecord.task_id` and `task_version`; resources under the ERP pack's `tasks/`; a manifest declaration; registry admission (unbound capability, duplicate `task_id`, widening budget); `DriverInput.allowed_capabilities` in `sdk/ports.py`, set by the run loop and enforced by the gateway and proposal handling; the driver's tool filter; the definition's TTL and budgets in the run; an acceptance check at run end; `ReasonCode.ACCEPTANCE_UNMET`.
- Tests and evidence: eight ERP definitions load, and a golden file records today's single tool set and each definition's chosen subset, every subset inside today's set (there is no per-task list today to copy); registry refusals, including a widening budget; a read and a proposal outside the run's set refused; the driver offers only the allowed tools; the definition's TTL replaces the global one; notes-domain definition; acceptance-unmet test. Plugin digests are re-pinned.
- Operations: the task catalog is unchanged in Phase 2; adding a task is a pack release, not a server change.

## Gates

Phase 2 Tasks 2c.1, 2c.2 and 2c.6, gate `full`, plus `pg` for 2c.1 and 2c.6.
