# ADR 0026: Plugin layout and a reusable core

Date: 2026-10-15. Status: Accepted (2026-10-15, owner; amended on acceptance: common plugin SDK). Refines ADRs 0002, 0012; HLD §4; [target architecture](../design/target-architecture.md) §15, §16 and the R3 row; [principles](../design/principles.md) PR-01, PR-03, PR-08, PR-10.

## Context

The [Phase 0–1 review](../reviews/2026-10-14-phase1-plugin-boundary-review.md) found that the boundary between the core and its plugins exists in metadata and import contracts but not in names, packaging or server code:
- R-1: the server hard-codes the `odoo19` auth placement and sandbox check that the Odoo manifest already declares (`server/bootstrap.py:38-39`), against accepted ADR 0012 item 1.
- R-2: the server and CLI import the ERP fixture package (`FakeErp`, `ScriptedErpDriver`, `SCENARIOS`), and those fixtures ship in the production `domain-erp` wheel.
- R-3: the generic profile schema lists the eight ERP task kinds as a `Literal` (`server/profile.py:53-67`), and the CLI holds the ERP demo prompts.
- R-4: `src/e_agent/erp/` sits beside `contracts/`, `sdk/` and `kernel/`, so a reader cannot tell that it is a plugin.

The owner asked on 2026-10-14 that plugins live in a plugins folder, that the layout leave room for many ERP providers (D1), and that the core be reusable for enterprise areas beyond ERP and for other agentic products (D2). The [X-agent adoption review](../reviews/2026-10-14-x-agent-adoption-review.md) adds two checks: a named "Plugins are guests" import contract (XA-02) and enforcement of declared capability requirements (XA-03; `CapabilityDescriptor.required_features` is declared at `contracts/capability.py:30` and never read).

## Decision

**Layout.**
- Plugins live under `src/e_agent/plugins/<area>/<package>`. `plugins/` and `plugins/<area>/` are namespace directories with no `__init__.py`, like `e_agent` and `e_agent.adapters` (ENG-ARCH-5).
- The ERP area is `plugins/erp/`: `domain/` (`e_agent.plugins.erp.domain`, distribution `domain-erp`), `odoo/` (`e_agent.plugins.erp.odoo`, distribution `adapter-odoo`, plugin id `odoo19`) and `simulator/` (`e_agent.plugins.erp.simulator`, distribution `adapter-erp-simulator`, plugin id `fixture-erp`). A new ERP system is a new sibling of `odoo/`.
- The domain pack and each provider are sibling packages, never nested, so the shared `dists/_hooks` sub-tree hook keeps each wheel independent.
- `contracts`, `sdk`, `kernel`, `server` and the infrastructure adapters (`adapters/{postgres,pydantic_ai,shacl,secretstore_local}`) are the core. The infrastructure adapters stay bootstrap-wired; making them discoverable plugins is Phase 3 and Phase 7 work (DR-04).
- **Filing rule.** A vendor that spans areas (for example Odoo for HR later) stays filed under its first area and binds the other area's domain through that domain's public API. This is recorded, not solved now.

**Import rules** (import-linter, `full` gate).
- *Core never imports plugins:* `e_agent.contracts`, `e_agent.sdk`, `e_agent.kernel` and `e_agent.server` never import `e_agent.plugins`.
- *Plugins are guests* (XA-02, PR-08): a plugin package never imports `e_agent.kernel`, `e_agent.server`, `e_agent.adapters.postgres`, `e_agent.adapters.secretstore_local`, `e_agent.adapters.pydantic_ai` or `e_agent.adapters.shacl`. Credentials reach a plugin only through `PluginServices`. A conformance test derives the plugin packages from the installed `e_agent.plugins.v1` entry points, so a new provider cannot sit outside the contract.
- A provider imports only its area's public domain API, never a sibling provider.

**Common plugin SDK** (owner amendment on acceptance, 2026-10-15).
- Every plugin builds on one common base: `e_agent.contracts` (portable records) and `e_agent.sdk` (ports, manifests, auth, errors and provider helpers), shipped as `e-agent-contracts` and `e-agent-plugin-sdk`. A plugin distribution depends on these two and, for a provider, its area's domain pack, and on no other e-agent distribution. A conformance test reads each plugin's `dists/<name>/pyproject.toml` and fails on any other e-agent dependency.
- *Connection spec.* The typed models for the manifest `connection` section (auth methods with their placement, and the sandbox probe) live in `e_agent.sdk.connection`. The host and every provider validate against that one definition, and an unknown placement is refused there. A plugin without a `connection` section needs none.
- *Rejections stay as they are.* `KnownNoEffectError` remains the one way a plugin tells the kernel that nothing was committed. No second rejection type is added.
- *Authenticated HTTP client* in `e_agent.sdk.http`, behind the optional extra `e-agent-plugin-sdk[http]`. It applies the `AuthContext`; it refuses a request to any host other than the connection's base-URL host (the egress allowlist from the adoption review); and it classifies a 4xx response as a transport-level rejection with an allow-listed code and a fixed safe message, and a 5xx, timeout or transport error as ambiguous. Provider bodies and headers are never logged or echoed, because they may carry submitted values or credentials. The executor keeps mapping a rejection to `KnownNoEffectError`, because a 4xx rejects this call and does not prove that an earlier call had no effect. The Odoo client moves onto it in Phase 1d, with behaviour unchanged.
- *The one boundary exemption.* The import contract "Core packages do not import agent frameworks or provider SDKs" gains one `ignore_imports` entry, `e_agent.sdk.http -> httpx`. The rest of the SDK stays free of `httpx`, and a consumer that does not install the extra never imports it.
- *Deferred:* a plugin conformance test kit in the SDK, until a third provider exists.

**Declared requirements** (XA-03, PR-10). `PluginRegistry.register()` refuses with `STARTUP_REJECTED` a binding template whose `supported_features` lacks any of its contract's `required_features`. Probing a live instance's features stays Phase 5.

**What moves out of the server.**
- *Auth placement and sandbox probe* come from the admitted plugins' manifest `connection` sections (ADR 0012 item 1). An unknown placement is refused, never defaulted, and a live provider whose manifest declares no sandbox probe makes startup refuse.
- *Task presets.* `PluginContribution.task_presets: tuple[TaskPreset, ...]`; `TaskPreset` holds the task kind, the demo prompt template, the default refs and the help text. `DriverConfig.task_kind` becomes `str`, validated at startup against the admitted presets. Phase 2 Task 2c.2 extends presets into task definitions (ADR 0028).
- *Driver factories.* `PluginContribution.driver_factories: Mapping[str, DriverFactory]`, keyed by `driver.kind`. A `DriverFactory` takes a `DriverRequest` (connection id, mode, task kind, refs) and returns an `AgentDriver`. The existing `drivers` field (ready instances) stays. The domain pack contributes the `scripted` factory, because live smoke tests also use it with Odoo.
- *Scripted-driver refs.* `DriverConfig.demand_ref` and `product_ref` fold into `refs` under the keys `demand_ref` and `product_ref`. The profile loader moves the two old top-level keys into `refs`, so existing local profiles keep loading. Their defaults come from the task preset.
- *The simulator* (`FakeErp`, its scenarios) becomes the discovered provider plugin `fixture-erp`. A fixture profile enables it as a live profile enables `odoo19`; a profile that does not enable it never imports it. `Runtime.fake_erp` is removed, and the CLI's create-call report reads a provider-neutral diagnostics hook.
- *No default profile.* The server package ships no profile. `load_profile()` needs a path or `E_AGENT_PROFILE`; the ERP fixture profile ships with the simulator plugin.

**Packaging.**
- `e-agent-server` no longer depends on `e-agent-domain-erp` or `e-agent-adapter-odoo`.
- New distributions: `e-agent-adapter-erp-simulator` (code) and `e-agent-erp` (no code; installs the server and the ERP plugins).
- The existing ten distribution names and versions stay; the public import names of the domain pack and the Odoo adapter change once, in Task 1d.10.
- `scripts/check_core_only.py` proves the core installs and serves `/health/ready` in a clean environment with no ERP wheel.

**Out of scope.** Run behaviour, the OpenAPI document and the event streams do not change. No runtime feature is added, so no toggle is needed (roadmap rule 3).

## Alternatives considered

- A flat `plugins/erp` plus `plugins/odoo`: rejected because it hides which providers belong to which area, and a second ERP provider would sit beside unrelated areas.
- `domains/erp` only, with providers left in `adapters/`: rejected because providers would still look like core adapters, which is R-4's problem.
- A top-level `plugins/<name>/` tree with its own `src/` per plugin: rejected because it contradicts the 2026-10-12 layout decision (one layer-grouped tree, no repeated folder names) and duplicates build configuration.
- Nesting providers inside the domain package (`erp/odoo`): rejected because the shared sub-tree hook would put Odoo into the `domain-erp` wheel, so the two distributions would no longer be independent.
- Keeping `demand_ref` and `product_ref` as top-level profile fields: rejected because they are ERP vocabulary in a generic schema (R-3); the loader alias keeps old profiles working.
- One import surface (the SDK re-exports every contract record, and plugins may not import `e_agent.contracts`): not chosen by the owner; the common base is contracts and SDK together.
- The HTTP helper as its own distribution instead of an SDK extra: rejected because it would add a release unit for one module; the extra plus one named `ignore_imports` entry keeps the SDK wheel free of `httpx` for consumers that do not need it.
- The HTTP helper raising `KnownNoEffectError` directly on a 4xx: rejected because only the executor knows whether an earlier call with the same operation identity may have committed.
- Checking capability requirements at call time instead of at registration: rejected because a missing feature would then fail silently mid-run (XA-03); the live feature probe that needs the instance stays in Phase 5.

## Consequences

- Code: `sdk/connection.py` and `sdk/http.py` (with the `http` extra on `dists/plugin-sdk`); the Odoo client on the SDK helper; `sdk/ports.py` (`TaskPreset`, `task_presets`, `DriverFactory`, `DriverRequest`, `driver_factories`); `kernel/registry.py` (manifest `connection` sections reachable; required-features check); `server/bootstrap.py`, `server/profile.py`, `server/cli.py` lose their ERP and `odoo19` literals; `erp/plugin.py` contributes presets and the scripted factory; the simulator package and its manifest; `pyproject.toml` import contracts; `dists/server`, `dists/adapter-erp-simulator`, `dists/bundle-erp`; the mover's `plugins` set.
- Tests and evidence: the Review Focus tests of the Phase 1d plan, including `test_live_provider_without_sandbox_probe_refuses_startup`, `test_live_profile_never_imports_simulator`, `test_two_erp_providers_routing`, `test_every_plugin_package_is_a_guest`, `test_binding_missing_required_feature_refused`, `test_server_has_no_domain_literals`, `test_plugin_dependencies_are_the_common_base`, `test_http_refuses_other_hosts`, `test_http_never_echoes_credentials` and `scripts/check_core_only.py`; unchanged OpenAPI and golden CLI prompts.
- Operations: profiles must be given (`--profile` or `E_AGENT_PROFILE`); the `Makefile` and README commands pass one. The owner re-pins `profiles/live-odoo19-learning.local.json` once after Task 1d.10, because the `domain-erp` and `odoo19` digests change.
- Documents: HLD §4, MVP §3, target §15, §16 and the R3 row, AGENTS.md repository map, ENG-ARCH-1 and ENG-ARCH-5 (Task 1d.10); principles PR-08 and PR-10 (Task 1d.11). The approved plan schedules these design updates with the code that makes them true, not with this ADR's acceptance.

## Gates

Phase 1d: Parts B and C start after the owner accepts this ADR (owner gate G1). Each task's gate set is in the [Phase 1d plan](../plans/2026-10-14-phase1d-plugin-boundary.md) "Gate" table, and the phase ends with the live check on `odoo19-learning`.
