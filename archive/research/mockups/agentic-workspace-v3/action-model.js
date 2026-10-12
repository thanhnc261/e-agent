// A shared presentation record for this prototype only; never an authorization model.
export function actionView(scenario, state) {
  const ownerOnly = state.clarification === "Project owner only";
  const audience = state.clarification || scenario.scope;
  const message = state.step === 1;
  const destination = message
    ? ownerOnly
      ? "Team chat / Direct message / Alex Morgan"
      : "Team chat / # delivery-meridian"
    : scenario.destination;
  const scope = message
    ? ownerOnly
      ? "Alex Morgan · project owner only"
      : "Delivery team · 8 internal members"
    : audience;
  const fields = message
    ? [
        ["Audience", scope],
        ["Attachment", "None"],
        ["Document link", "DOC-DEMO-084"],
      ]
    : scenario.fields.map(([key, value]) => [
        key,
        key === "Visibility" && state.clarification ? audience : value,
      ]);
  return {
    title: message
      ? ownerOnly
        ? "Share with the project owner"
        : "Share with the delivery team"
      : scenario.artifact,
    action: message ? "Post one message" : scenario.action,
    destination,
    scope,
    fields,
    identity: "Jamie Lee · example delegated identity",
    workspace: "Northstar · example workspace",
    connection: message
      ? "Team chat · connection revision 3"
      : scenario.destination.split(" / ")[0] + " · connection revision 3",
    revision: state.revision,
    disclosure: message
      ? `Sample access check: document and message content cleared for ${scope}.`
      : `Sample access check: content limited to ${scope}.`,
    body: message ? "Meridian handoff is ready" : scenario.body,
    text: message
      ? "The delivery handoff is ready for review: Meridian · Delivery handoff (DOC-DEMO-084). Please review the scope and confirm your next steps before the 19 October kickoff."
      : scenario.text,
    recordId: message
      ? "MSG-DEMO-029"
      : { service: "SR-208", procurement: "PO-DEMO-084" }[state.scenario] ||
        "DOC-DEMO-084",
    sources: scenario.sources.map((source) => source[1]),
  };
}
export function sampleReadBack(action) {
  return {
    action: structuredClone(action),
    observedAt: "9 October 2026 · 14:32 UTC (sample)",
    verifier: "Independent read-back service · fixture",
    outcome: "Observed values match the approved action",
  };
}
