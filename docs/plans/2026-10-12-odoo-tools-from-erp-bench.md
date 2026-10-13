# Odoo integration tools derived from ERP-Bench (phased plan)

> **For agentic workers:** this is a spec-level phased plan. Each phase gets its own detailed plan (superpowers:writing-plans) when it starts. Execute with superpowers:subagent-driven-development. Phases marked `[OWNER]` stop for an owner decision first.

**Goal:** give the agent the Odoo 19 read and write tools that real procurement and manufacturing work needs, derived from the ERP-Bench task patterns. With them it can:
- answer ERP questions;
- plan buy, make or mix supply under policy;
- execute the plan as linked, approved, verified documents (SO → MO → PO → invoice).

**Design anchor:** [target architecture](../design/target-architecture.md):
- §10 integration (domain → capability → binding → connection)
- §2.3 domain packs and task definitions
- §6 external-feedback correction
- roadmap **P3 integration breadth**

**Divergence from the design, stated:** P3 calls for a *second, non-ERP* domain pack to prove genericity. The owner chose depth in ERP first, so this plan deepens the ERP pack. The G2/G3/G10 genericity gates stay open until a second domain exists.

**Hard dependency:** this plan is **not standalone**. Phases 3–5 need core plan Phases 2–3 ([core plan](2026-10-12-core-conversation-cognition.md)):
- task definitions with fixed tool sets: about 18 tools today, about 60 after this plan;
- the ContextAssembler, so tool output doesn't flood context;
- grounded answers;
- multi-write action plans (Phase 0.3 here).

Phases 0–2 can run in parallel with the core plan.


> **Phase order is governed by the [roadmap](../roadmap.md)** (owner decision 2026-10-12): action plans (Phase 0.3 here) are built in roadmap Phase 2 (execution IR); this plan is roadmap Phase 5. Every new runtime feature here ships behind a profile toggle (`off/shadow/on`) with a fallback to the existing path before any write is reserved.

**Status:** Proposed. Nothing implemented.

## Source pin (decision D7, implementation-plan §8)

| Field | Value |
|---|---|
| Name | ERP-Bench (Odoo 19 benchmark from the paper "Preventing Artifact Drift in Agent Benchmark Generation") |
| Local checkout | `/Users/thanhnguyen/dev/lab/onto-erp-agents/experiment/substrate/erp-bench` (nested, git-ignored) |
| Revision | `880a1a0aca6eeffa2fecccd07458b58f8795d313` (2026-09-04) |
| Licence | CC0 1.0 Universal |
| Identity | Hugging Face dataset with Croissant metadata (`croissant.json`) |
| Canonical URL | **`[OWNER]` to supply.** The checkout has no git remote configured, and I won't guess one. |
| Content used by this plan | Task **instructions** (`tasks/*/instruction.md`) and the **specification schema** (`schemas/models.py`) only |
| Content never used | `tasks/*/solution/` (reference plans), `tasks/*/tests/` (verifiers), rewards, and any held-out data. Reused task texts are labelled development examples, not evaluation (implementation-plan §8, ADR 0010). |

Runtime code never imports from the bench checkout or the experiment. Any reused concept is re-authored with provenance (a rule-to-source map). The `odoo-bench` container and the `onto-erp-agents`/`enterprise-agent` experiments are **never** a target and are never modified.

## What ERP-Bench needs (from 300 instructions, 29 patterns)

**Patterns:**
- **Buy-only**, with variants: baseline, net-30, immediate invoicing, fixed or percentage down payment, screened vendors, seeded drafts.
- **Manufacture-only**, with variants: no buy route, policy-forbidden buying, no available vendors.
- **Single BOM**, with variants: lowest cost, split by capacity, single workcenter, invoicing.
- **Subassemblies**, with variants: single, shared-overflow capacity, qualified workcenters, restricted, parallel, serial, branch-assigned.
- **Repair plan** (easy, medium, hard): a supplier cancels a confirmed PO, and the agent re-plans with minimal change.

**Every task asks the agent to:**
1. **Read:**
   - customer order requests (quantity, due date, pre-tax budget cap, acceptance rules);
   - finished and component stock;
   - products (list price, cost, routes);
   - vendor offers (price, lead time, min/max quantity, horizon-wide totals);
   - internal notes on vendors, customers, stock and workcenters (hidden constraints such as maximum order quantity or capacity minutes);
   - BOMs and subassemblies;
   - workcenters (minutes per unit, capacity, qualified alternatives);
   - existing draft or confirmed SOs, POs and MOs;
   - payment terms.
2. **Decide:** accept or reject orders, then choose buy, make or mix under a minimum portfolio new-spend margin, budget caps, capacity, min/max quantities, consolidation (one PO per offer) and vendor-count minimisation. In repair tasks, minimise change.
3. **Write, with lineage:**
   - Create and confirm SOs: list price, commitment date, payment terms.
   - Cancel failing SOs.
   - Create and confirm POs: origin = SO or MO refs, delivery date, consolidated per offer.
   - Cancel the broken PO (repair tasks).
   - Create and confirm MOs: origin = SO or parent MO, start and due dates, workcenter on each work order.
   - Create and post customer invoices, including down payments.

**Tension with e-agent's trust anchor:** instructions say "Work with full autonomy. Do not ask the user for confirmation". e-agent requires an approval for every write. Phase 0.1 settles this.

## Global constraints

- Trust anchor unchanged unless ADR 0024 says otherwise:
  - writes are proposals;
  - approval binds the exact normalised plan or action;
  - admission, reservation and connection busy rules apply per write;
  - independent read-back verification;
  - UNKNOWN is never blindly replayed.
- Each capability has:
  - a domain contract in the right bounded context (`procurement`, `inventory`, `manufacturing` (new), `sales`, `receivables` / `invoicing`);
  - an adapter binding;
  - a bridge method that calls `_check_target()` first and filters company and namespace;
  - a projection with explicit keys (no pass-through of provider rows);
  - a verifier for every write.
- Never touch `odoo-bench` or any container except `odoo19-learning-*`, `e-agent-ledger` and containers this plan creates. Never read bench solutions or tests.
- Bridge version bumps update every pin (adapter enum, example profile, sandbox script, tests, runbook). The sandbox is upgraded with `-u e_agent_bridge` only.
- End to end after every task: full gate, Postgres, `make e2e`. A live check on the sandbox at each phase exit.

---

## Phase 0: decisions and kernel prerequisite `[OWNER]`

| Task | Deliverable |
|---|---|
| 0.1 `[OWNER]` | **ADR 0024 approval model for multi-step plans.** (a) *Recommended:* the agent proposes an **action plan**, an ordered set of writes with dependencies and lineage. The human approves the plan's exact digest once, and the kernel executes it write by write under the existing admission, reservation and verification rules. Any deviation (stale facts, a changed price, a failed step) stops it and returns findings. (b) A profile flag auto-approves writes in a declared benchmark environment only. That touches the trust anchor, needs a threat-model entry, and must never be enabled in live profiles (`/health/ready` reports it, like `self_approval_allowed`). |
| 0.2 `[OWNER]` | **Evaluation substrate.** (a) Port task *patterns* to synthetic variants seeded in `odoo19-learning` under new `e-agent-bench-*` namespaces (cheap; no bench environment). (b) Run selected bench task environments in throwaway containers this project owns (closer to the source; heavier). Either way, the bench verifier is not used as the product verifier, since e-agent needs its own, and reused tasks are development examples. |
| 0.3 | **Kernel: action plans (multi-write runs).** Today `Budgets.max_admitted_writes = 1` and every write tool is "exactly one". New contract `ActionPlan(steps: tuple[PlannedAction, ...])`, where each step has `depends_on` and lineage refs to earlier steps' results (for example a PO `origin` = SO name once the SO exists). The plan is validated as a whole by domain rules, approved as one digest, then dispatched in dependency order with per-step receipts and verification. Partial-failure semantics: the run stops, finished steps stay committed and verified, and the remainder is reported. This needs core plan Phase 2–3, plus its own ADR (0025). |
| 0.4 | Record the D7 pin above in `docs/implementation-plan.md` §8 and the ADR index once the owner supplies the URL. |

**Exit:** ADRs 0024 and 0025 accepted; substrate chosen; the action-plan kernel contract designed (implemented in Phase 3).

---

## Phase 1: capability inventory and Odoo mapping

**Deliverable:** `docs/integration/odoo-erp-bench-capability-map.md`, a matrix with one row per concept used by the 29 patterns. Columns:
- the bench concept (`schemas/models.py` class and field);
- the Odoo 19 model and fields;
- read or write;
- the e-agent bounded context;
- the proposed contract id;
- the rules involved;
- the verifier read-back.

**Concept → Odoo 19 mapping (starting point, to be verified against Odoo 19 source):**

| Concept | Odoo 19 |
|---|---|
| Customer, vendor and notes | `res.partner` (`comment`, `customer_rank`, `supplier_rank`, `property_payment_term_id`, `property_supplier_payment_term_id`, `credit_limit`) |
| Product, price, cost, routes | `product.product` / `product.template` (`list_price`, `standard_price`, `route_ids`, `default_code`) |
| Vendor offer | `product.supplierinfo` (`partner_id`, `price`, `delay`, `min_qty`, plus max quantity and notes from the bench's custom fields or partner notes; to verify) |
| Stock | `stock.quant` by `stock.location` / `stock.warehouse`, plus `product.qty_available` and `virtual_available` |
| BOM | `mrp.bom`, `mrp.bom.line` |
| Workcenter, capacity, notes | `mrp.workcenter` (`time_efficiency`, `costs_hour`, `note`), `mrp.routing.workcenter` (operations, `time_cycle_manual`) |
| SO | `sale.order` (`commitment_date`, `payment_term_id`, `origin`, `state`), `sale.order.line` |
| PO | `purchase.order` (`origin`, `date_planned`, `state`), `purchase.order.line` |
| MO | `mrp.production` (`origin`, `date_start`, `date_deadline`, `bom_id`), `mrp.workorder` (`workcenter_id`) |
| Invoice and down payment | `account.move` (`out_invoice`, `invoice_payment_term_id`, `invoice_origin`, `state`), down-payment wizard `sale.advance.payment.inv` |
| Payment terms | `account.payment.term` |

**Exit:** the map has been reviewed. Every pattern's needs are covered by named contracts, and gaps are marked.

---

## Phase 2: read capabilities (list and detail)

Read-only, so it is safe to build in parallel with the core plan. Each read is company- and namespace-scoped, capped (`limit`, `complete` flag), projected to explicit keys, and paged through `after` cursors where lists can be long.

| Bounded context | Capability (proposed id) | Returns |
|---|---|---|
| `sales` | `sales.orders.list.v1`, `sales.order.read.v1` | SOs by state, customer and date window; one SO with lines, commitment date, terms, origin links |
| `purchase` (or `procurement`) | `purchase.orders.list.v1`, `purchase.order.read.v1` | POs by state, vendor and date; one PO with lines, origin, date_planned |
| `manufacturing` (new) | `manufacturing.orders.list.v1`, `manufacturing.order.read.v1`, `manufacturing.bom.read.v1`, `manufacturing.workcenters.list.v1` | MOs with work orders and workcenters; BOM with components and subassemblies; workcenters with time per unit, capacity and notes |
| `inventory` | `inventory.products.search.v1`, `inventory.stock.read.v1` | Product search by name or code with price, cost and routes; stock per product and warehouse |
| `procurement` | `procurement.vendor-offers.read.v1` (extends `offers`) | Offers with price, lead time, min/max quantity and vendor notes |
| `partners` (in `sales` / `procurement`) | `partners.search.v1`, `partner.read.v1` | Customers or vendors with notes, payment terms and credit limit |
| `invoicing` | `invoicing.invoices.list.v1`, `invoicing.payment-terms.list.v1` | Customer and vendor invoices with state and residual; payment terms |

Every list read's answer goes through the **grounded answer contract** (core plan Phase 3), so "list all POs" ends verified with citations. Until then, these reads are usable only inside tasks.

**Exit:**
- Live on the sandbox: "list all POs", "show stock for X", "who supplies X and at what min/max", "what does workcenter Y allow" are each answered and cited.
- Bridge guard tests cover every new method.
- Adapter projection tests drop unknown keys.

---

## Phase 3: write capabilities as plan steps

**Requires** Phase 0.3 action plans and ADR 0024.

| Capability | Contract essentials | Rules (examples, from patterns) | Verifier read-back |
|---|---|---|---|
| `sales.order.create-confirm.v1` | customer, product, quantity, list price, commitment date, payment term | list price required, budget cap (pre-tax), acceptance window | SO confirmed with exact lines and terms |
| `sales.order.cancel.v1` | SO ref and reason | only orders failing acceptance; no invoice exists | SO cancelled |
| `purchase.order.create-confirm.v1` | vendor offer, quantity, date_planned, origin refs | offer min/max as horizon totals; one PO per offer; vendor note limits; route allowed | PO confirmed; origin contains the SO or MO refs |
| `purchase.order.cancel.v1` | PO ref and reason (repair) | only the disrupted PO | PO cancelled; demand not re-sent to the same vendor path |
| `manufacturing.order.create-confirm.v1` | BOM, quantity, start and due dates, origin, workcenter per operation | capacity minutes horizon-wide per workcenter; qualified workcenters only | MO confirmed; work orders on the assigned workcenters |
| `invoicing.customer-invoice.create-post.v1` | SO ref, payment term, down payment (fixed or %) | only retained SOs; exactly one invoice per SO; terms match | Invoice posted and linked to the SO |

Each write is idempotent through the bridge operation key (namespace plus logical operation), reconcilable after UNKNOWN, and exposed only as a step of an action plan.

**Plan-level validation:**
- New domain rules evaluate the whole plan: portfolio new-spend margin, budget caps, capacity sums, min/max totals, lineage completeness and consolidation.
- Rules live in the procurement and manufacturing domain packs as SHACL shapes or rule code per the existing rule inventory, with provenance to the pattern they came from.

**Exit:** a buy-only and a single-BOM synthetic scenario on the sandbox go from proposal to plan approval to dispatch to verification of every step, with lineage visible in Odoo.

---

## Phase 4: planning support

Large tasks need allocation decisions that a local model will not compute reliably by hand.

| Task | Deliverable |
|---|---|
| 4.1 | **Plan feasibility tool** (`procurement.plan.check.v1`, read-only): given a draft plan, it returns the margin, budget, capacity, min/max and lineage findings before proposal. It is the same rule code as plan validation, exposed as a read, so the model can iterate cheaply. |
| 4.2 `[OWNER]` | **Optional solver tool**: a domain service that proposes a feasible or optimal allocation (CP-SAT, as the bench's own generator uses). It is powerful, but in a benchmark setting it changes what is being measured, so the owner decides whether it is product scope and how evaluation reports it. |
| 4.3 | Guidance and task definitions per pattern family (buy-only, make, subassembly, repair) with acceptance specs. |

---

## Phase 5: evaluation

| Task | Deliverable |
|---|---|
| 5.1 | Synthetic scenario fixtures per pattern family in the fixture provider (deterministic CI). |
| 5.2 | Live development runs on the chosen substrate (Phase 0.2). Report per task: plan validity, verification results, number of approvals, tokens, time. Use ADR 0010 metrics (pass@1 in development; pass^3 for a frozen candidate). |
| 5.3 | Never mix product runs with the experiment's confirmatory evidence. The `onto-erp-agents` and `enterprise-agent` experiments stay untouched. |

---

## Phase map and cost

| Phase | Size (tasks) | Depends on | Owner gates |
|---|---|---|---|
| 0 Decisions + action-plan design | 4 | none | ADR 0024 approval model, substrate, canonical URL |
| 1 Capability map | 1 doc | 0.4 | review |
| 2 Read capabilities | about 7 (one per context) | 1; grounded answers from core Phase 3 for chat answers | none |
| 3 Write capabilities as plan steps | about 6 + plan rules | 0.3 (action plans), core Phases 2–3 | ADR 0025 |
| 4 Planning support | 3 | 3 | solver scope |
| 5 Evaluation | 3 | 2–4 | none |
