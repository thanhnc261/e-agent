# QA: <study name>

Date: <YYYY-MM-DD>.

## Commands run

| Command | Result |
|---|---|
| `node research/mockups/<folder>/verify.mjs` | <pass/fail, with counts> |

## Mechanics verified

- Viewports: <list>
- Themes: <list>
- Keyboard and focus: <path and result>
- Console errors and external requests: <result>
- Automated accessibility: <tool and result>

## Self-review against the rubric

<Findings, in the ag-ux-review finding format. List those fixed in this study separately from those still open.>

## Design-system conformance

| Requirement | Result | Evidence |
|---|---|---|
| <each AG-DS criterion and each design-system requirement in e-agent.md, one row per ID> | <score> | <where> |

## Screenshots inspected

<A list of the paths in `screenshots/` that were looked at, not just generated.>

## Limits

This QA does not establish:
- real assistive-technology behaviour;
- real-device behaviour;
- moderated user evaluation;
- live integration.

Script checks verify mechanics only.
