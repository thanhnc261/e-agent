// Authored sample exchanges only. These do not interpret arbitrary intent or alter actions.
export const followupQuestions = [
  "What did you use to prepare this?",
  "What happens next?",
  "Who will have access?",
];
export function highlights(scenario, action) {
  if (!scenario.fields) return [];
  if (scenario.category === "Finance")
    return action.fields.filter(([name]) =>
      ["Supplier", "Quantity", "Total"].includes(name),
    );
  return action.fields.slice(0, 3);
}
export function answerFollowup(question, scenario, task, action) {
  if (question === followupQuestions[0]) {
    return scenario.blocked
      ? "The people directory is unavailable in this example. No employee records have been read."
      : `I used ${scenario.sources.map(([name, revision]) => `${name} (${revision})`).join("; ")}. You can inspect the excerpts using the source links. These are sample records, not live reads.`;
  }
  if (question === followupQuestions[2]) {
    return scenario.blocked
      ? "Access has not been granted. Connection setup belongs to the workspace administrator."
      : `The scope shown for this ${scenario.readOnly ? "answer" : "action"} is ${action.scope}. ${scenario.readOnly ? "Reading this answer makes no changes to source permissions." : `The destination is ${action.destination}. Approval applies only to the displayed action; it does not grant new access.`}`;
  }
  if (question === followupQuestions[1]) {
    if (scenario.blocked)
      return "An administrator needs to configure the people directory connection. Your request stays in this conversation.";
    if (scenario.readOnly)
      return "Check the regional spending limit with the policy owner before booking. The employee’s region is not available in this sample, so no specific limit can be confirmed.";
    if (task.scene === "unknown")
      return "Check the existing result. Do not resend: the first action may already have completed. If the check remains unresolved, an operator needs to investigate.";
    if (task.scene === "stale")
      return "Prepare a fresh review and inspect its terms before approving. The outdated revision cannot be used.";
    if (task.scene === "verifying")
      return "Check the external result against the approved action. Approval by itself is not evidence that the work succeeded.";
    if (task.scene === "done")
      return "Inspect the sample read-back records in the workspace. This example has no further action waiting for approval.";
    if (task.scene === "rejected")
      return "No action was sent for the rejected proposal. You can return to review it; earlier completed actions stay unchanged.";
    return scenario.next && !task.step
      ? "Review the document’s scope and terms, then approve that exact action. After its result is checked, I’ll prepare the sharing message for a separate review. Approving the document does not approve posting the message."
      : "Review the destination, audience and material values in the workspace. Confirm the exact action there. Its outcome must then be checked separately.";
  }
  return "Your message is saved in this sample conversation; it has not changed the proposal. This mockup has no live model. Try one of the suggested follow-ups to explore a prepared exchange.";
}
