# Review response

Date: 2026-10-10. Claude inspected source and screenshots; it did not run tests. The original review is preserved in `CLAUDE-REVIEW.md`. Its assessment is not owner acceptance.

- **Chat prominence:** reduced desktop workspace to 44%, including when navigation expands. Added assertions that chat remains wider than the workspace with navigation collapsed and expanded. The explicit action button stays in the document review where its terms are displayed.
- **Thread context:** workspace open/closed state and selected tab now live with each conversation. Returning restores them as well as the draft. A regression restores the Sources tab in an open workspace.
- **Dismissed sample chooser:** the close-button path clears pending prompt text. This fix was already underway when Claude read the earlier snapshot; added a regression for close-with-X followed by a welcome starter.
- **Message audience:** the message review can narrow its audience. A document already restricted to its owner cannot be widened by selecting a larger message audience. Earlier read-back records retain their original approved scope. Reopening a rejected unchanged proposal does not invent a new revision.
- **Simulation reset:** completed and uncertain states cannot jump straight back to an unsent review. `Restart example` explicitly resets sample records and action progress; other simulated transitions only appear before the first write.
- **Mobile context:** added a visible Chat label to the workspace close control. Mobile deliberately switches surfaces rather than squeezing in another composer. Long documents scroll and full action content is repeated in confirmation; no claim that all terms are simultaneously visible.
- **Starter count/navigation:** three optional shortcuts keep the empty conversation quiet; the explicit sample chooser offers all six. History expands the drawer, while the panel control toggles it. This remains a minor discoverability tradeoff to evaluate with the owner.

The final browser regression was rerun after the changes; see QA.md. No production implementation or user acceptance is implied.
