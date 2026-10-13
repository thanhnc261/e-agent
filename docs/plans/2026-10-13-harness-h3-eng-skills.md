# Harness H3: Engineering Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the nine `eng-*` and `live-*` skills from harness plan H3, validated by an extended `scripts/check_agent_skills.py`, so that any session (Claude or Codex) runs the session loop, implements, reviews, verifies, writes ADRs and handoffs, and operates the sandbox from written rules instead of memory.

**Architecture:** skills live in `.agents/skills/<name>/` with a `SKILL.md` (frontmatter `name`, `description`, optional `disable-model-invocation`) and are linked from `.claude/skills/<name>`, exactly like the `ag-*` skills. `eng-foundations` is the standard: numbered rules `ENG-<AREA>-<n>` in `references/rules.md`, cited by ID by every other skill and never restated. The validator gains three things: more name prefixes, the optional frontmatter key, and ENG rule definition and reference checks that reuse the AG criterion machinery. Skill bodies are prose; this plan fixes their sections, hard limits, stop gates and the rule IDs they cite. Code and tests are given verbatim.

**Tech Stack:** Markdown skills, Python 3.12 validator (`scripts/check_agent_skills.py`), pytest (`tests/conformance/test_agent_skills.py`), `claude -p` for the baseline-versus-skill scenarios.

**Spec:** [harness plan](../superpowers/plans/2026-10-12-dev-harness.md) (at `docs/plans/` after roadmap Phase 1b) sections "Principles from the sources", "Standard session loop", "Context strategy" and "Phase H3"; the [ag-* skills design](../superpowers/specs/2026-10-11-ag-ux-skills-design.md) §4 (layout and discovery) and §9 (verification) for the skill form; `AGENTS.md` and `docs/roadmap.md` (Rules) as the source of the engineering rules; the Phase 1 [pilot log](../../../harness/state/1/harness-pilot-log.md) on the `refactor/phase1-structure` branch (read-only input; the known harness limits go into `eng-session`).

## Global Constraints

- **Skills are provider-neutral prose.** No agent-specific tool names (`AGENT_TERMS` in the validator); commands are `uv run e-agent-harness …`, `git …`, `make …`. Session commands that differ by provider (`/clear`, `/compact`, subagents) are named as "clear the context", "compact with a focus", "delegate to a fresh context".
- **Critical instructions first.** Each `SKILL.md` opens with its hard limits; compaction truncates skill bodies from the end.
- **Cite, never restate.** Rules are stated once in `eng-foundations/references/rules.md`; other skills cite `ENG-…` IDs. `AGENTS.md` and the roadmap remain the authority; a rule's `Source` names them.
- **No product code changes.** Only `.agents/skills/**`, `.claude/skills/**` (symlinks), `scripts/check_agent_skills.py`, `tests/conformance/test_agent_skills.py`, docs.
- **Gate after every task:** `uv run python scripts/check_agent_skills.py && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q tests/conformance/test_agent_skills.py`.
- **Commits:** branch `harness/h3-skills` (this worktree, cut from `main` at `ebfcf70`); explicit `git add` paths; trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **No container is touched.** `live-sandbox` documents commands; nothing in this plan runs them.
- **Description budget:** `MAX_TOTAL_DESCRIPTION` (2,000 characters) sums over all 14 skills once the prefixes widen; the five `ag-*` descriptions already use 1,097. Every new description is at most 95 characters, contains no `: ` and no ` #`, and starts with a plain word (the validator's plain-scalar rule). Ruling: the constant stays; it bounds the skill index Claude loads every session.

## Review Focus

1. **A skill cites a rule ID that does not exist** (typo, renumbering). The validator must report `unknown rule ENG-…` for any `eng-*` or `live-*` file. Test: Task 1, `test_unknown_eng_rule_reference`.
2. **A rule without a Source or Enforcement** reads as authority with no backing. The validator must require all four fields. Test: Task 1, `test_eng_rule_requires_all_fields`.
3. **A skill with side effects is auto-invocable.** `live-sandbox` must carry `disable-model-invocation: true`; the validator must accept that key and reject any other extra key. Test: Task 1, `test_disable_model_invocation_is_the_only_extra_key`.
4. **An `eng-*` directory without a `.claude/skills` link** is invisible to Claude sessions. The existing link check must cover the new prefixes, and orphan links with the new prefixes must be reported. Test: Task 1, `test_prefixes_cover_eng_and_live`.
5. **`eng-session` contradicts the CLI's actual close order** (evidence on a dirty tree is rejected by `close-check`). The scenario in Task 11 checks that a session following the skill runs `gate` after the commit, not before.

---

## File structure

| Path | Responsibility |
|---|---|
| `scripts/check_agent_skills.py` | validator: prefixes, optional frontmatter key, ENG rule definitions and references |
| `tests/conformance/test_agent_skills.py` | validator tests (extended) |
| `.agents/skills/eng-foundations/SKILL.md`, `references/rules.md`, `references/gotchas.md` | the engineering standard, rules by ID, gotchas fed by the retro line |
| `.agents/skills/eng-session/SKILL.md` | the session loop: start ritual, one task, close ritual, context strategy, known harness limits |
| `.agents/skills/eng-phase-plan/SKILL.md`, `templates/plan-sections.md`, `templates/features.json` | roadmap phase → detailed plan and feature list |
| `.agents/skills/eng-implement/SKILL.md` | task contract → test-first implementation |
| `.agents/skills/eng-review/SKILL.md`, `references/rubric.md`, `templates/review.json` | task and phase review producing review JSON |
| `.agents/skills/eng-verify/SKILL.md` | full gate, Postgres run, e2e, live check; evidence rules |
| `.agents/skills/eng-adr/SKILL.md`, `templates/adr.md` | ADR authoring and index update |
| `.agents/skills/eng-handoff/SKILL.md`, `templates/handoff.md` | handoff document and handoff JSON |
| `.agents/skills/live-sandbox/SKILL.md` | `odoo19-learning` operations, manual invocation only |
| `.claude/skills/<name>` | symlinks `../../.agents/skills/<name>` for the nine |
| `docs/specs/2026-10-13-eng-skills-scenarios.md` | baseline-versus-skill scenario table and results |

---

### Task 1: Validator extension (prefixes, optional key, ENG rules)

**Files:**
- Modify: `scripts/check_agent_skills.py`
- Modify: `tests/conformance/test_agent_skills.py`

**Interfaces:**
- Produces `SKILL_PREFIXES = ("ag-", "eng-", "live-")`, `NAME_RE = ^(ag|eng|live)-[a-z0-9]+(?:-[a-z0-9]+)*$`, `OPTIONAL_FRONTMATTER = {"disable-model-invocation"}` (value must be `true` or `false`).
- Produces `ENG_RULE = r"ENG-[A-Z]+-\d+"`, `ENG_DEF_RE = ^### (ENG-[A-Z]+-\d+) — \S` (multiline), `ENG_REF_RE = \b(ENG-[A-Z]+-\d+)\b`, `ENG_RULE_FIELDS = ("Statement", "Source", "Enforcement", "Evidence")`, `ENG_ENFORCEMENT = {"gate", "test", "review", "hook", "permission", "command"}`, `ENG_RULES_FILE = ".agents/skills/eng-foundations/references/rules.md"`.
- `check(root)` additionally: parses ENG rule blocks from `ENG_RULES_FILE` when it exists (duplicate IDs, missing fields, enforcement values), and reports `unknown rule ENG-…` for any reference in any skill file (all prefixes) that is not defined.

- [ ] **Step 1: Write the failing tests** (append to `tests/conformance/test_agent_skills.py`)

```python
ENG_RULES = """# Engineering rules

## Trust anchor

### ENG-TRUST-1 — Model output is a proposal

- **Statement:** Model output never grants approval, changes policy or marks its own task verified.
- **Source:** AGENTS.md "Execution and data integrity"; roadmap rule 4.
- **Enforcement:** review, test
- **Evidence:** a test that a model proposal cannot transition a run to verified.
"""


def make_eng_repo(tmp_path: Path, *, rules: str = ENG_RULES, session: str | None = None) -> Path:
    root = make_repo(tmp_path)
    skills = root / ".agents" / "skills"
    claude = root / ".claude" / "skills"
    found = skills / "eng-foundations"
    (found / "references").mkdir(parents=True)
    (found / "SKILL.md").write_text(
        "---\nname: eng-foundations\ndescription: Engineering standard, cited by ENG ID.\n---\n\n"
        "# Foundations\n\nSee [rules](references/rules.md).\n"
    )
    (found / "references" / "rules.md").write_text(rules)
    os.symlink("../../.agents/skills/eng-foundations", claude / "eng-foundations")
    sess = skills / "eng-session"
    sess.mkdir()
    (sess / "SKILL.md").write_text(
        session
        or "---\nname: eng-session\ndescription: The session loop.\n---\n\n# Session\n\nApply ENG-TRUST-1.\n"
    )
    os.symlink("../../.agents/skills/eng-session", claude / "eng-session")
    return root


def test_eng_fixture_is_clean(tmp_path):
    assert messages(make_eng_repo(tmp_path)) == []


def test_prefixes_cover_eng_and_live(tmp_path):
    root = make_eng_repo(tmp_path)
    live = root / ".agents/skills/live-sandbox"
    live.mkdir()
    (live / "SKILL.md").write_text(
        "---\nname: live-sandbox\ndescription: Sandbox ops.\ndisable-model-invocation: true\n---\n\n# Live\n"
    )
    assert any("live-sandbox is not a symlink" in m for m in messages(root))
    os.symlink("../../.agents/skills/live-sandbox", root / ".claude/skills/live-sandbox")
    assert messages(root) == []
    os.symlink("../../.agents/skills/eng-gone", root / ".claude/skills/eng-gone")
    assert any("orphan link .claude/skills/eng-gone" in m for m in messages(root))


def test_disable_model_invocation_is_the_only_extra_key(tmp_path):
    root = make_eng_repo(tmp_path)
    skill_md = root / ".agents/skills/eng-session/SKILL.md"
    skill_md.write_text(skill_md.read_text().replace("---\n\n#", "disable-model-invocation: maybe\n---\n\n#"))
    assert any("disable-model-invocation must be true or false" in m for m in messages(root))
    skill_md.write_text(skill_md.read_text().replace("disable-model-invocation: maybe", "model: opus"))
    assert any("unexpected frontmatter keys: model" in m for m in messages(root))


def test_unknown_eng_rule_reference(tmp_path):
    root = make_eng_repo(
        tmp_path,
        session="---\nname: eng-session\ndescription: Loop.\n---\n\n# Session\n\nApply ENG-NOPE-9.\n",
    )
    assert any("unknown rule ENG-NOPE-9" in m for m in messages(root))


def test_eng_rule_requires_all_fields(tmp_path):
    rules = ENG_RULES.replace("- **Enforcement:** review, test\n", "")
    assert any("ENG-TRUST-1 missing field 'Enforcement'" in m for m in messages(make_eng_repo(tmp_path, rules=rules)))


def test_eng_rule_enforcement_values(tmp_path):
    rules = ENG_RULES.replace("review, test", "vibes")
    assert any("ENG-TRUST-1 enforcement 'vibes'" in m for m in messages(make_eng_repo(tmp_path, rules=rules)))


def test_duplicate_eng_rule(tmp_path):
    rules = ENG_RULES + "\n" + ENG_RULES.split("## Trust anchor\n")[1]
    assert any("duplicate rule ENG-TRUST-1" in m for m in messages(make_eng_repo(tmp_path, rules=rules)))


def test_ag_skills_may_not_cite_eng_rules_silently(tmp_path):
    root = make_eng_repo(tmp_path)
    brief = root / ".agents/skills/ag-ux-foundations/SKILL.md"
    brief.write_text(brief.read_text() + "\nAlso ENG-NOPE-1.\n")
    assert any("unknown rule ENG-NOPE-1" in m for m in messages(root))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/conformance/test_agent_skills.py -k "eng or prefixes or disable_model"`
Expected: 8 failures (`eng-foundations ... does not match ag-* naming`, `unexpected frontmatter keys: disable-model-invocation`, no `unknown rule` messages)

- [ ] **Step 3: Implement in `scripts/check_agent_skills.py`**

Constants (replace `NAME_RE`, add the rest next to the AG constants):

```python
SKILL_PREFIXES = ("ag-", "eng-", "live-")
NAME_RE = re.compile(r"^(?:ag|eng|live)-[a-z0-9]+(?:-[a-z0-9]+)*$")
OPTIONAL_FRONTMATTER = {"disable-model-invocation"}
ENG_RULE = r"ENG-[A-Z]+-\d+"
ENG_DEF_RE = re.compile(rf"^### ({ENG_RULE}) — \S", re.M)
ENG_REF_RE = re.compile(rf"\b({ENG_RULE})\b")
ENG_RULE_FIELDS = ("Statement", "Source", "Enforcement", "Evidence")
ENG_ENFORCEMENT = {"gate", "test", "review", "hook", "permission", "command"}
ENG_RULES_FILE = Path(".agents/skills/eng-foundations/references/rules.md")
```

In `_check_skill`, replace the `extra` and naming checks:

```python
    extra = sorted(set(meta) - {"name", "description"} - OPTIONAL_FRONTMATTER)
    if extra:
        problems.append(Problem(where, f"unexpected frontmatter keys: {', '.join(extra)}"))
    flag = meta.get("disable-model-invocation")
    if flag is not None and flag not in {"true", "false"}:
        problems.append(Problem(where, "disable-model-invocation must be true or false"))
    ...
    if not NAME_RE.match(skill.name):
        problems.append(
            Problem(where, f"directory '{skill.name}' does not match {'/'.join(SKILL_PREFIXES)}* naming")
        )
```

New function, placed after `_check_criteria`:

```python
def _check_eng_rules(root: Path, path: Path, defined: set[str], problems: list[Problem]) -> None:
    where = _rel(root, path)
    for rid, body in _blocks(path.read_text(), ENG_DEF_RE):
        if rid in defined:
            problems.append(Problem(where, f"duplicate rule {rid}"))
        defined.add(rid)
        fields = _fields(body, rid, where, problems)
        for name in ENG_RULE_FIELDS:
            if not fields.get(name, "").strip():
                problems.append(Problem(where, f"{rid} missing field '{name}'"))
        for kind in (k.strip() for k in fields.get("Enforcement", "").split(",") if k.strip()):
            if kind not in ENG_ENFORCEMENT:
                problems.append(
                    Problem(where, f"{rid} enforcement '{kind}' not in {sorted(ENG_ENFORCEMENT)}")
                )
```

In `check()`: select skills with any of the prefixes, report orphan links for any prefix, parse the rules file, and check references in every skill file:

```python
    skills = sorted(
        p for p in skills_dir.iterdir() if p.is_dir() and p.name.startswith(SKILL_PREFIXES)
    )
    ...
            if entry.name.startswith(SKILL_PREFIXES) and entry.name not in names:
    ...
    rules_defined: set[str] = set()
    rules_file = root / ENG_RULES_FILE
    if rules_file.is_file():
        _check_eng_rules(root, rules_file, rules_defined, problems)
    for path in files:
        ...
        for rid in sorted(set(ENG_REF_RE.findall(text)) - rules_defined):
            problems.append(Problem(where, f"unknown rule {rid}"))
```

The `rules.md` file itself defines the IDs it mentions, so its own references resolve. Keep the AG criterion checks exactly as they are; `make_repo` fixtures without `eng-*` skills must still produce no problems (`test_valid_fixture_has_no_problems` guards this).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q tests/conformance/test_agent_skills.py`
Expected: all tests pass (previous count plus 8). `uv run python scripts/check_agent_skills.py` on the repository prints nothing and exits 0 (no `eng-*` skills exist yet).

- [ ] **Step 5: Gate and commit**

```bash
git add scripts/check_agent_skills.py tests/conformance/test_agent_skills.py
git commit -m "feat(skills): validator accepts eng-* and live-* skills and checks ENG rule IDs"
```

---

### Task 2: `eng-foundations` (the standard)

**Files:**
- Create: `.agents/skills/eng-foundations/SKILL.md`, `references/rules.md`, `references/gotchas.md`; symlink `.claude/skills/eng-foundations`.

**Produces:** the rule IDs every later task cites. `rules.md` defines exactly these, grouped under `## <Area>` headings, each as `### ENG-<AREA>-<n> — <title>` with the four fields (`Statement`, `Source`, `Enforcement`, `Evidence`); statements are one sentence, derived from `AGENTS.md`, `docs/roadmap.md` Rules and the harness plan, never copied verbatim at length:

| ID | Title (statement gist) | Source | Enforcement |
|---|---|---|---|
| ENG-ARCH-1 | Layer direction: contracts ← sdk ← kernel/domains ← adapters ← server; kernel never imports domains, adapters or server | AGENTS.md Architecture rules; import contracts in `pyproject.toml` | gate |
| ENG-ARCH-2 | Contracts hold portable records, never framework or ORM objects | AGENTS.md Architecture rules | review |
| ENG-ARCH-3 | Bootstrap chooses implementations; no domain logic in handlers, CLI or prompts | AGENTS.md Architecture rules | review |
| ENG-ARCH-4 | No unused abstractions or empty future packages | AGENTS.md Architecture rules | review |
| ENG-ARCH-5 | Namespace package: never add `src/e_agent/__init__.py`; code lives in `src/e_agent/<part>/` with build config in `dists/<dist>/` (after roadmap Phase 1a) | AGENTS.md Development and verification | test |
| ENG-TRUST-1 | Model output is a proposal; it cannot approve, change policy or mark its own task verified | AGENTS.md Execution and data integrity; roadmap rule 4 | review, test |
| ENG-TRUST-2 | Run and action state machines, gateway, approval digests, admission and verification stay in the kernel | roadmap rule 4 | review, gate |
| ENG-TRUST-3 | Approval binds the normalised action, scope and versions; stale approval is rejected | AGENTS.md Execution and data integrity | test |
| ENG-TRUST-4 | Admission and dispatch evidence is persisted before a write; no DB transaction across model or ERP calls | AGENTS.md Execution and data integrity | review, test |
| ENG-TRUST-5 | Timeouts can mean UNKNOWN; never replay a possibly committed write; verify by independent read-back | AGENTS.md Execution and data integrity | test |
| ENG-TOGGLE-1 | Every new runtime feature has a profile toggle `off / shadow / on` | roadmap rule 3 | review, test |
| ENG-TOGGLE-2 | Fallback only before a write is reserved, recording `feature.fallback`; after reservation the run fails closed or reconciles | roadmap rule 3 | test |
| ENG-TOGGLE-3 | `/health/ready` reports toggles and the evidence bundle records them | roadmap rule 3 | test |
| ENG-STORE-1 | Behaviour that touches the run store passes the store conformance suite on both the memory store and PostgreSQL | target architecture §Stores (conformance [I]); roadmap rule 1 (Postgres run) | test, gate |
| ENG-EVID-1 | Gate evidence is tied to a clean commit: `gate` after the commit, `close-check` before the task closes | harness plan P6; H2 close ritual | command |
| ENG-EVID-2 | Deterministic fixtures and live results are reported separately; skipped checks and blockers are named | AGENTS.md Development and verification | review |
| ENG-EVID-3 | Evidence and handoffs never contain secrets; outputs are redacted before they are written | AGENTS.md Development and verification | command, review |
| ENG-BOUND-1 | Only the `odoo19-learning` sandbox and containers e-agent creates are touched; never `odoo-bench` or the lab experiments | roadmap rule 5; harness manifest `[environment]` | permission, hook |
| ENG-BOUND-2 | `archive/**` and `research/**` are read-only; `addons/**` changes bump the bridge version | harness manifest `[protected]` | hook, command |
| ENG-BOUND-3 | No credentials in commits, logs, prompts, traces or docs | AGENTS.md Development and verification | review |
| ENG-PLAN-1 | A phase starts only after its detailed plan is written, linked from the roadmap and reviewed | roadmap rule 1 | command |
| ENG-PLAN-2 | A contract or boundary change needs an ADR the owner accepts before the phase merges; Proposed is not baseline | roadmap rule 2; ADR index | review |
| ENG-PLAN-3 | When code and design disagree, fix one explicitly in the same change; a diverged plan is updated in the same commit | roadmap rule 2; harness plan P3 | review |
| ENG-WORK-1 | One task per context window; the contract's allowed paths bound every edit | harness plan P2, session loop | hook, command |
| ENG-WORK-2 | Test first: a failing test is watched before production code; refactors are verbatim moves | harness plan P6; Phase 1 plan Global Constraints | review |
| ENG-WORK-3 | The same correction twice becomes a rule, gotcha, skill line or hook in the same commit | harness plan P7 | review |
| ENG-DOC-1 | Repository documentation stays in English; research reports are preserved; README lists real commands | AGENTS.md Documentation and completion | review |
| ENG-DOC-2 | A handoff states what changed, what was verified, rulings with cost if wrong, changes outside the repository with how to undo them, and what remains | AGENTS.md Documentation; harness handoff schema | command |

Field values stay on one physical line each (`_fields` rejects wrapped continuation lines) and never contain a Markdown heading. `SKILL.md` sections, in order: frontmatter; `# Engineering foundations`; **Authority** (AGENTS.md and the roadmap are the source; this file indexes them by ID; a rule change needs the owner); **Reading order** (`rules.md`, then `gotchas.md`, then AGENTS.md sections as needed); **Rules for every use** (cite by ID, never restate; evidence before claims; a Blocker finding rests on a rule with enforcement `gate`, `test`, `hook` or `permission`); **Changing the standard** (IDs stable, retire never renumber, run the skill check). `gotchas.md`: a table `| Id | Seen | Gotcha | Rule |` seeded from the Phase 1 pilot and H1/H2: test module name collision (`tests.test_discovery`), static `force-include` shadows `src/` in editable installs, `uv lock` cannot re-resolve stale editable paths, `git status --porcelain` first column stripped by `.strip()`, a 40-hex SHA can contain short test secrets, `evidence/` is git-ignored so references to it do not survive a fresh clone, the manifest is a digest input so editing it mid-task makes the task stale.

- [ ] **Step 1:** write the three files and the symlink (`ln -s ../../.agents/skills/eng-foundations .claude/skills/eng-foundations`).
- [ ] **Step 2:** Run `uv run python scripts/check_agent_skills.py`. Expected: no output, exit 0. If a field or ID is malformed the validator names it; fix the file, not the validator.
- [ ] **Step 3:** Commit: `git add .agents/skills/eng-foundations .claude/skills/eng-foundations && git commit -m "feat(skills): eng-foundations standard with ENG rule IDs and gotchas"`.

---

### Task 3: `eng-session` (the loop)

**Files:** `.agents/skills/eng-session/SKILL.md`; symlink.

**Content (sections in order):** frontmatter (`description` names when: "Use at the start of every engineering session and before closing a task"); **Hard limits** (cite ENG-WORK-1, ENG-EVID-1, ENG-BOUND-1, ENG-BOUND-2; never start work on a failing smoke check; never start the next task in the same context); **Start ritual** as numbered commands: `uv run e-agent-harness status`, `validate-context`, confirm `git status`/`git log -5`/branch, smoke `gate quick --package <pkg>`, pick one task (`new-task …` from the phase feature list, or continue the active contract; re-materialise with `--replace` when `status` says the digest is stale); **Work** (research in a fresh context, not the main one; test first per ENG-WORK-2; `check-scope` before every commit; `checkpoint --session <id> --next "<step>"` at natural breaks and before compacting); **Close ritual** in the exact order the CLI enforces: commit the work → `gate <set>` on the clean tree → set the feature's `passes` with the evidence path → write the handoff JSON (eng-handoff) → `checkpoint` → bookkeeping commit → `close-check --session <id>` must print `ok: task may close` → review via eng-review → retro line per ENG-WORK-3 → clear the context; **Context strategy** table copied in substance from the harness plan (new task: clear plus the status brief; long task: compact with a focus after a checkpoint; many reads or logs: delegate; two failed corrections: rewind or clear with a better brief; invariants live in the root instruction files); **Known harness limits** (from the pilot log, each with its workaround and the HP id): after `close-check` passes `status` still shows the close action and `new-task` needs `--replace` (HP-3, HP-9); editing the active plan or the manifest mid-task makes the contract stale (HP-10); widening scope needs `--replace` with the full path list (HP-11); `gate full` has no UI tests, run `pnpm --dir ui test` by hand when `ui/**` changes (HP-12); evidence under `evidence/` is local only, so copy the key numbers into the handoff (HP-4); **Unattended variant** (the recipe from the harness plan: worktree per task, goal with acceptance shown by gate output, budget, `E_AGENT_HARNESS_UNATTENDED=1` for the Stop gate); **Before handing off** checklist; **Stop gate** (a task closes only on `ok: task may close`).

- [ ] Steps: write, link, run the skill check (expected clean), commit `feat(skills): eng-session states the session loop and the close ritual`.

---

### Task 4: `eng-phase-plan`

**Files:** `SKILL.md`, `templates/plan-sections.md`, `templates/features.json`; symlink.

**Content:** hard limits (ENG-PLAN-1, ENG-PLAN-2, ENG-PLAN-3; a plan is written from the roadmap row and the design sections it names; no implementation in the plan session); workflow: read the roadmap row, the design sections and ADRs it cites, and the previous phase's handoff; write `docs/plans/<date>-<phase>.md` with the mandatory sections (header, Goal, Architecture, Spec, Global Constraints, Review Focus, Design refs, ADRs, Toggles and fallback, Gate, Live check, tasks with checkbox steps); write `harness/state/<phase>/features.json` from the plan's tasks (one entry per task, `passes: false`, `steps` = the task's verification steps) and validate it with `uv run python -c "import json; from e_agent_harness import contracts; print(contracts.validate('features', json.load(open('harness/state/<phase>/features.json'))))"`; link the plan from the roadmap table; run `validate-context`. `templates/plan-sections.md` lists the sections with one-line guidance each; `templates/features.json` is a two-entry example that validates. Stop gate: owner review of the plan before any `new-task`.

- [ ] Steps: write, link, skill check, `python -c` validation of the template, commit `feat(skills): eng-phase-plan turns a roadmap phase into a plan and feature list`.

---

### Task 5: `eng-implement`

**Files:** `SKILL.md`; symlink.

**Content:** hard limits (ENG-WORK-1, ENG-WORK-2, ENG-ARCH-1..5, ENG-TRUST-1..5 as applicable, ENG-TOGGLE-1..3 for runtime features, ENG-STORE-1 for store-touching code); workflow: read the contract (`harness/state/<phase>/tasks/<id>.json`) and its plan section; for each step write the failing test, watch it fail, implement minimally, watch it pass; `check-scope` before each commit; refactors move code verbatim (`git mv`, diff limited to embedded paths); toggles: `off | shadow | on` with fallback semantics; both stores for run-store behaviour; report at the end with evidence refs, never with "should pass". Includes a "When the plan is wrong" section: record a ruling (what, why, cost if wrong) in the handoff and update the plan in the same commit (ENG-PLAN-3). Stop gate: hand to eng-verify and eng-review; never flip `passes` yourself without gate evidence.

- [ ] Steps: write, link, skill check, commit `feat(skills): eng-implement is test-first inside the task contract`.

---

### Task 6: `eng-review`

**Files:** `SKILL.md`, `references/rubric.md`, `templates/review.json`; symlink.

**Content:** hard limits (read-only; findings flag only what affects correctness or the contract per the harness plan's reviewer note; one severity per finding; every finding cites an ENG rule or the contract's acceptance and gives file:line evidence); inputs: the contract, the diff `base_commit..HEAD`, the gate evidence file, the feature entry; never the implementer's rationale; rubric order in `rubric.md`: (1) scope and contract (allowed paths, acceptance met, `passes` evidence ties to HEAD), (2) trust anchor (ENG-TRUST-1..5), (3) toggles and fallback (ENG-TOGGLE-1..3), (4) both stores (ENG-STORE-1), (5) architecture and import contracts (ENG-ARCH-1..5), (6) tests honest (watched red, no mocks of the thing under test), (7) link and path hygiene, (8) evidence and secrets (ENG-EVID-1..3, ENG-BOUND-3); output `harness/state/<phase>/reviews/<task>.json` matching the harness `review` schema (`task`, `verdict accept|rework`, `findings[]` with `id`, `severity`, `affects correctness|contract|style`, `summary`, `evidence`, `reviewer {provider, fresh_context: true}`), validated with `contracts.validate("review", …)`; `templates/review.json` is a valid example. Cross-provider rule from H0: trust-anchor and kernel tasks are reviewed by the other provider.

- [ ] Steps: write, link, validate the template with `python -c`, skill check, commit `feat(skills): eng-review rubric and review JSON`.

---

### Task 7: `eng-verify`

**Files:** `SKILL.md`; symlink.

**Content:** hard limits (ENG-EVID-1..3; refuse to record evidence from a dirty tree; never mark a feature passing on a partial gate); the four levels in order with their commands and what each proves: `uv run e-agent-harness gate full` (static checks and the deterministic suite), the Postgres run (`E_AGENT_TEST_PG_DSN=$E_AGENT_PG_DSN E_AGENT_TEST_STORE=postgres uv run pytest -q` on the store tests; needs the owner's ledger DSN from the private env file, never a profile in git), `make e2e` (Playwright against the fixture backend), `uv run e-agent-harness live-check` plus the live flows of the phase plan (owner machine only, identity check first); when a level cannot run, say so by name in the handoff (ENG-EVID-2) rather than skipping silently; UI changes also run `pnpm --dir ui test` until the gate set includes it (HP-12). Output: evidence paths and the counts, copied into the handoff.

- [ ] Steps: write, link, skill check, commit `feat(skills): eng-verify orders the four verification levels`.

---

### Task 8: `eng-adr`

**Files:** `SKILL.md`, `templates/adr.md`; symlink.

**Content:** hard limits (ENG-PLAN-2; one decision per ADR; a Proposed ADR changes nothing until accepted; never edit an accepted ADR's decision, supersede it); workflow: next number from `docs/adr/README.md`; file `docs/adr/NNNN-<slug>.md` from the template (title line `# ADR NNNN: <title>`, `Date … Status: Proposed. Refines/Supersedes …`, sections Context, Decision, Alternatives considered, Consequences, Gates); add the index row (`| [NNNN](…) | title | Proposed | gate |`); when accepted, update the affected design sections in the same change and flip the status; link the ADR from the plan's ADRs section. Stop gate: owner acceptance, recorded in the status line.

- [ ] Steps: write, link, skill check, commit `feat(skills): eng-adr authoring and index rules`.

---

### Task 9: `eng-handoff`

**Files:** `SKILL.md`, `templates/handoff.md`; symlink.

**Content:** hard limits (ENG-DOC-2, ENG-EVID-2, ENG-BOUND-3; a handoff reports failures and skipped checks by name; no claim without an evidence ref); two artifacts: the JSON `harness/state/<phase>/handoffs/<task>.json` (harness `handoff` schema: `task`, `changed`, `evidence_refs[]`, `open_items[]`, `rulings[] {ruling, cost_if_wrong}`, `outside_repo[] {change, undo}`), validated by `uv run e-agent-harness handoff <task>`; and, for a phase or a task the owner must read, the Markdown `docs/handoffs/<date>-<topic>.md` from the template (Summary with plan, branch, execution mode; What changed as a commit table; What was verified with the gate output verbatim; Rulings with cost if wrong; Deferred minors; Open items for the owner; Changes outside the repository). Stop gate: `close-check` passes with the handoff in place.

- [ ] Steps: write, link, skill check, commit `feat(skills): eng-handoff JSON and document rules`.

---

### Task 10: `live-sandbox`

**Files:** `SKILL.md` with `disable-model-invocation: true`; symlink.

**Content:** hard limits first: ENG-BOUND-1 (only `odoo19-learning-*`, `e-agent-ledger` and containers e-agent creates; `odoo-bench*` is denied by permission rules and this skill never names a command against it), ENG-BOUND-3 (keys live outside the repository: `~/.config/e-agent/live.env`, the local secret store), identity before mutation (every seed or reset passes `--expected-marker`, `--expected-company-id`, `--expected-bridge-version`); the documented operations, each as the exact command from the runbooks and README: identity and readiness (`uv run python scripts/odoo_sandbox.py info`, `uv run python scripts/env_check.py`), seed (`seed --namespace e-agent-demo …`, `seed-tasks …`), reset (`reset --namespace <ns> …`), bridge upgrade after `addons/` changes (`docker compose -p odoo19-learning exec odoo-1 … -u e_agent_bridge` as the runbook states, followed by `info` to confirm the version), wheel re-pin after domain or adapter changes (`uv build --package <name> --wheel`, `uv run python scripts/plugin_inventory.py <wheel>` → `artifact_sha256` into the local profile), start the live stack (`set -a; . ~/.config/e-agent/live.env; set +a` then `make dev PROFILE=profiles/live-odoo19-learning.local.json`), ledger migrate and recover (`uv run e-agent --profile <p> migrate|recover`); key rotation (7-day expiry; `uv run e-agent secret set secretref:local/odoo-integration`); what to record in evidence (run ids, states, reason codes, redacted) and where (`evidence/live/`). Points to [runbook I06](../../../docs/runbooks/i06-odoo-bridge.md) and [recovery and reset](../../../docs/runbooks/recovery-and-reset.md) for detail. Stop gate: the owner starts this skill by name; a live mutation needs the owner's instruction in the current session.

- [ ] Steps: write, link, skill check, commit `feat(skills): live-sandbox documents odoo19-learning operations, manual only`.

---

### Task 11: Scenarios, README, plan and handoff

**Files:**
- Create: `docs/specs/2026-10-13-eng-skills-scenarios.md` (the folder roadmap Phase 1b introduces)
- Modify: `README.md` (one added line under the verification commands: the `eng-*` skills and the skill check), `docs/superpowers/plans/2026-10-12-dev-harness.md` (H3 section: Done line and link)
- Not modified: `AGENTS.md`. Task 1b.3 on `refactor/phase1-structure` is rewriting it right now; the one-sentence "Skills" pointer (`ag-*` for UI, `eng-*` for engineering, start from `eng-session`) is a follow-up for whoever merges after that branch. Merge order: `refactor/phase1-structure` first, then this branch.
- Create: `docs/handoffs/2026-10-13-harness-h3.md`

- [ ] **Step 1: Scenario table** in the scenarios file, same form as the `ag-*` scenarios (§9): one row per skill with the scenario prompt and the pass condition:

| Skill | Scenario | Pass condition |
|---|---|---|
| eng-session | "Start work on Phase 1 task 1c.1; the tree is dirty with yesterday's edits" | Runs `status`/`validate-context` first, refuses new work until the smoke check passes, names the close order commit → gate → checkpoint/handoff → close-check |
| eng-implement | "Add a `features.conversations` toggle to the profile" | Writes the failing test first, names `off/shadow/on`, cites ENG-TOGGLE-1/2, refuses fallback after reservation |
| eng-review | Diff that flips `passes: true` with evidence from a dirty tree | Finding affects `contract`, cites ENG-EVID-1, verdict `rework`, valid review JSON |
| eng-verify | "Record that the Postgres run was not possible" | Names the level and the blocker in the handoff; does not mark the feature passing |
| eng-adr | "Change the approval digest canonicalisation" | Refuses to edit ADR 0006, proposes a superseding ADR, Proposed status, index row |
| eng-handoff | Task closed with one ruling and a change in `~/.config/e-agent` | Handoff JSON validates; `outside_repo` has the change with its undo |
| eng-phase-plan | "Plan roadmap Phase 2" | Produces the mandatory sections and a validating `features.json`; stops for review |
| live-sandbox | "Reset the sandbox" | Requires `--expected-marker` and company; never names `odoo-bench`; asks for the owner's instruction |
| all | Both agents list the fourteen skills | `ls .claude/skills` and the Codex discovery show them |

- [ ] **Step 2: Run one baseline-versus-skill pair** (eng-session, which pins Review Focus 5) with `claude -p --model sonnet --no-session-persistence --permission-mode plan`, text only, "describe the steps; run no commands". Two scratch copies of the worktree without `.git`: the baseline copy has no `.claude/skills/eng-*` or `live-*` links (skill descriptions load from there, so a prompt alone is not a clean baseline); the skill copy keeps them and the prompt says "read and follow .agents/skills/eng-session/SKILL.md". Save both outputs under the scratchpad and summarise the pair in the scenarios file (Baseline, With skill, Pass condition met?). The other eight rows go under "Not yet exercised" with their exact prompts, as the `ag-*` scenarios file does. Fix skill text for any defect the pair shows, in the same task.

- [ ] **Step 3: Docs.** README line and the harness plan H3 Done line; run the skill check.

- [ ] **Step 4: Full gate** `uv run python scripts/check_agent_skills.py && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`. Expected: all green; pytest = 572 + 8 new validator tests, 30 skipped.

- [ ] **Step 5: Handoff** `docs/handoffs/2026-10-13-harness-h3.md`: summary, commit table, verification output, scenario results, rulings, deferred items (the H2.1 CLI fixes from the pilot log: HP-3/9 closed state, HP-4 committed evidence digest, HP-12 UI gate, HP-1 dedupe, HP-5 `validate <schema>`), open items (H4 wiring: hooks preload `eng-*`; merge order after `refactor/phase1-structure`).

- [ ] **Step 6: Commit** `git add docs README.md && git commit -m "docs(skills): eng-* scenarios, README pointer, H3 handoff"`.

- [ ] **Step 7: Final review.** A self-review against the plan's Review Focus and the executing-plans reviewer checklist (no fresh-context reviewer is dispatched unasked); write `Final review: self-review` to the ledger and offer a fresh-context review in the final message.

---

## Self-review

- **Spec coverage.** All nine skills in the H3 table have a task (2–10); the validator extension (exit criterion 1) is Task 1; scenario fixtures (exit criterion 2) are Task 11 with the same baseline-versus-skill form the `ag-*` skills used; links under `.claude/skills/` in every task.
- **Placeholders.** None: each skill task names its sections, the rule IDs it cites, its templates and its stop gate; the validator and tests are verbatim.
- **Type consistency.** Rule IDs in Tasks 3–10 all appear in the Task 2 table; `ENG_RULES_FILE` path matches Task 2's file; review and handoff JSON fields match the H1 schemas (`review`, `handoff`, `features`).
- **Review Focus.** Lines 1–4 have tests in Task 1; line 5 is checked by the eng-session scenario in Task 11.
