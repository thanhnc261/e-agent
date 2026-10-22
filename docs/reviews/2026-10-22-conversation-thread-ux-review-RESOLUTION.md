# Review resolution: conversation thread UI (Phase 4, gate G-D)

- **Review:** [2026-10-22-conversation-thread-ux-review.md](2026-10-22-conversation-thread-ux-review.md)
- **Resolved by:** Claude (Phase 4 subagent-driven development), 2026-10-22. Owner G-D answer: "Fix all".
- **Revision:** `a592890b` (UI code at `356341f4`; later commits are docs and review records only)

The owner answered G-D directly. The advisor delegation used for G-B and G-C did not continue. "Fix all" is read as: fix 4.U1 to 4.U7 and the five flagged VI rows (V-1 to V-4), and accept the 68 unflagged VI rows of the review's "New VI since G-B" table. The VI rows that the fixes themselves added or changed are listed below for confirmation.

| Finding | Resolution | Evidence |
|---|---|---|
| 4.U1 | Fixed. Sources first lists the earlier runs used as hints, from the bundle's `conversation.carried_run_ids`, only for a run pinned `conversations: on`. A quiet read raises no alert when it fails (GD-1). Opening a hint opens that run in the workspace, as its card's Open does; the mockup instead focused the card in the thread (coordinator ruling). | `0d79968c`, `8544f1ef`; `ui/packages/ui-conformance/tests/carried.spec.ts`; `selectCarriedRuns` unit tests |
| 4.U2 | Fixed. The full-view workspace head carries `StopSlot` (stop rules unchanged, EA-4) and `ConnectionStatus`. | `d81db1a7`, `09dcfee1`; the 390 px specs in `conversation.spec.ts` |
| 4.U3 | Fixed. A conversation opens at its latest run card without moving focus, with no animation under reduced motion. It uses `block: "start"`: measured at 390×844, `"end"` left the composer below the fold. The thread head is now sticky, so the stream status stays in view (GD-2), and the scroller's `scroll-padding-top` keeps a focused control from sitting under the head (GR-1, WCAG 2.4.11). | `1f88eb5d`, `b1707ef0`, `356341f4`; the 390×844 Docked spec and the focus-not-obscured spec |
| 4.U4 | Fixed. The inner scroll region is kept (coordinator ruling: page scroll would touch the 40 % layout and T4-2). The workspace head is sticky, an `aria-hidden` scroll cue shows while more is below (a dashed edge under forced colours), and bringing the decision into view no longer scrolls the head out (scrollTop on open was 127, now 0). | `a21f886f`, `09dcfee1`; the 1280×800 ten-field spec |
| 4.U5 | Fixed. "Open the decision" only opens. When the decision is already shown, it selects the Decision tab and focuses the workspace heading. `aria-expanded` was dropped. | `2387733a` |
| 4.U6 | Fixed. A single `translateServerValue` helper maps the server's enum values to i18n keys, with the value lists taken from the server contracts and the verbatim value as fallback. "Verified" appears only for OutcomeStatus `VERIFIED`. The outcome row's label is built from that allow-list, so an unknown status reads the neutral "Outcome reported" (GD-3), and the row no longer repeats its label. The unused keys `event.outcome.reported` and `outcome.references` are deleted. | `d60ecf5a`, `0eab058b` |
| 4.U7 | Fixed. Under forced colours only the selected workspace tab is underlined. | `1e7440e9`; `forced-colors.spec.ts` workspace state |
| V-1 to V-4 | Fixed as listed in the table below. V-3: the user's task is "yêu cầu" everywhere, in 9 keys. `context.noHost` is the one exception, because its VI is owner-confirmed F-7 copy pinned by `ui/apps/web/test/routes.test.ts` (see open items). | `6e4805a2`, `4403a7f4`; `ui/packages/ui-core/test/text.test.ts` |

**Fix reviews.**
- `harness/state/4/reviews/4e.7-fixes.json`: rework, GD-1 to GD-6.
- `4e.7-fixes-r2.json`: rework, GR-1.
- `4e.7-fixes-r3.json`: the final scoped re-review.
- UI architecture §12 describes the fixes (GD-5): `eb543338`, `9a8eb109`.

**Known open items from the handoffs**, as the review ruled:
- T4-7 is confirmed as a deviation from the mockup that breaks no criterion.
- E5-3 is fixed as 4.U6.
- E5-5 is rejected: in `on`, a mismatched citation stops the answer before any `proposal.created` is written.
- R5-1 is rejected as stated; its two unused keys are deleted.
- EA-14's dashed border is rejected: it stays visible.
- E5-1 option (b) remains an unbuilt follow-up that needs an ADR.

## New VI since G-D

These rows were added or changed by the fixes, after the owner's G-D answer. Each one needs the owner's confirmation.

| Key | EN | VI | Old VI |
|---|---|---|---|
| `carried.title` | Used earlier runs as hints | Đã dùng các lượt trước làm gợi ý | (new) |
| `carried.note` | Hints only: e-agent reads the records again before relying on them. | Chỉ là gợi ý: e-agent đọc lại bản ghi trước khi dựa vào chúng. | (new) |
| `citation.valueNotRecorded` | Value not recorded | Giá trị không được ghi lại | Không ghi lại giá trị |
| `nav.lastSeen` | last seen | thấy lần cuối | lần cuối |
| `explain.revision` | Revision | Bản sửa đổi | Phiên bản |
| `conversation.refusedBusy` | This conversation is busy. Wait, decide the approval, or stop the task. | Cuộc trò chuyện đang bận. Hãy chờ, quyết định phê duyệt, hoặc dừng yêu cầu. | … hoặc dừng tác vụ. |
| `run.nothingRunning` | Nothing is running | Không có yêu cầu nào đang chạy | Không có tác vụ nào đang chạy |
| `thread.legacyNote` | Earlier task · not part of a conversation | Yêu cầu trước · không thuộc cuộc trò chuyện nào | Tác vụ trước · không thuộc cuộc trò chuyện nào |
| `nav.legacy` | Earlier tasks · this session · last seen | Các yêu cầu trước · phiên này · trạng thái thấy lần cuối (fix round 1, GD-6) | Tác vụ trước · phiên này · trạng thái lần cuối (then "Yêu cầu trước · phiên này · trạng thái lần cuối" in `6e4805a2`) |
| `outcome.groundedExplain` | Grounded: its sources are records this task read. Not verified: nothing read the result back independently. | Có dẫn chứng: nguồn là các bản ghi mà yêu cầu này đã đọc. Chưa xác minh: chưa có bước kiểm tra độc lập nào đọc lại kết quả. | … mà tác vụ này đã đọc. … |
| `explain.absent` | Opening this reads the task's audit record. | Mở mục này sẽ đọc hồ sơ kiểm tra của yêu cầu. | … của tác vụ. |
| `explain.partial` | Part of this task is not recorded, so the explanation is partial. | Một phần của yêu cầu không được ghi lại, nên phần giải thích chưa đầy đủ. | Một phần của tác vụ … |
| `explain.stale` | Read before the task's latest change. | Được đọc trước thay đổi mới nhất của yêu cầu. | … của tác vụ. |
| `explain.label.grounded` | Grounded in this task's records | Có dẫn chứng từ bản ghi của yêu cầu này | Có dẫn chứng từ bản ghi của tác vụ này |
| `value.validation.PASS` | Passed | Đạt | (new) |
| `value.validation.FAIL` | Failed | Không đạt | (new) |
| `value.validation.UNKNOWN` | Unknown | Chưa rõ | (new) |
| `value.validation.ERROR` | Could not be checked | Không kiểm tra được | (new) |
| `value.decision.approved` | Approved | Đã phê duyệt | (new) |
| `value.decision.rejected` | Rejected | Đã từ chối | (new) |
| `value.receipt.COMMITTED` | Committed (fix round 1, GD-6) | Đã ghi vào hệ thống (fix round 1, GD-6) | (new); first shipped as "Recorded" / "Đã ghi nhận" in `d60ecf5a` |
| `value.receipt.FAILED` | Failed | Thất bại | (new) |
| `value.receipt.UNKNOWN` | Unknown | Chưa rõ | (new) |
| `value.stage.succeeded` | Succeeded | Thành công | (new) |
| `value.stage.failed` | Failed | Thất bại | (new) |
| `value.stage.blocked` | Blocked | Bị chặn | (new) |
| `value.stage.unknown` | Unknown | Chưa rõ | (new) |
| `value.stage.skipped` | Skipped | Đã bỏ qua | (new) |
| `value.stage.started` | Started | Đã bắt đầu | (new) |
| `value.stage.waiting` | Waiting | Đang chờ | (new) |
| `value.outcome.VERIFIED` | Verified | Đã xác minh | (new) |
| `value.outcome.FAILED` | Check failed | Kiểm tra không đạt | (new) |
| `value.outcome.UNKNOWN` | Unknown | Chưa rõ | (new) |

Removed in EN and VI: `event.outcome.reported` and `outcome.references`.

## Checks re-run

Both commands were run from the repository root on `a592890b`.

| Command | Result |
|---|---|
| `pnpm --dir ui check` | exit 0: "All matched files use Prettier code style!"; "Test Files  31 passed (31)", "Tests  258 passed (258)"; "✔ no dependency violations found (179 modules, 522 dependencies cruised)"; "ok  no provider identifiers in ui/" |
| `pnpm --dir ui conformance` | exit 0: "219 passed (1.9m)", "4 skipped" (the two reference-UI tests, `overlay-visual` and `visual-review`, as at review time); 0 failed; axe found 0 violations in every state checked |

Limits: these are browser-mechanics checks on the conformance mock API. No real `on` server was used, and there was no assistive-technology, device or user testing. The new focus spec covers the stack and page layouts but not the split layout, and it runs in Chromium only (GS-1, Low).

## Open items for the owner

Answered 2026-10-22. The owner replied "Ask advisor and continue" to the two questions below and delegated both to the advisor:

1. **The "New VI since G-D" rows:** accepted as listed. They were reconciled against the i18n diff, reviewed twice, and none claims verification that its EN does not.
2. **`context.noHost`:** changed from "tác vụ" to "yêu cầu", so the user's task is "yêu cầu" everywhere (V-3). This is task 4.R2, commit `dfeeadb`; the pinned F-7 test in `ui/apps/web/test/routes.test.ts` is updated.

Follow-ups, not built:

- `RuleFindings.tsx:24` in the approval card still shows raw rule statuses such as PASS. `translateServerValue("validation", …)` already exists for it.
- Labelling free-text answer fields as model-authored needs an ADR (E5-1 option b).
