# Claude project guidance

@AGENTS.md

AGENTS.md above is the shared instruction source for repository conventions, architecture boundaries, safety invariants and verification; follow it before working in this repository. Read [docs/high-level-design.md](docs/high-level-design.md) and [docs/mvp-detailed-design.md](docs/mvp-detailed-design.md) for the implementation baseline.

Current repository status: early implementation (see README status table). Do not assume live integrations, an ERP sandbox or UI exist. Inspect the actual checkout and report implementation versus proposal accurately.

Keep Claude-specific instructions here only when necessary; do not duplicate the full shared rules or maintain a second architecture specification. Current user instructions take precedence over repository guidance.

# Compact instructions

When compacting, keep: the active task contract id and its file path; the full list of modified files; the gate commands run and their last result; open review findings; and the single next action.
