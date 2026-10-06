# ADR 0007: durable run events over SSE; framework UI protocols are adapters

Date: 2026-10-06. Status: Accepted (project owner, decisions D1–D5, 2026-10-06).

## Context

ADR 0001 adds a streaming overlay UI. Pydantic AI natively emits AG-UI and Vercel AI data-stream events, including tool-approval streaming. Those protocols describe the *conversation*. The business record is the kernel's `RunEvent` sequence: proposal, findings, approval request, dispatch, receipt, outcome. If the UI is driven by framework events, approvals would be expressed in framework terms and reconnect semantics would follow the framework's lifetime, not the ledger's.

## Decision

1. **Canonical contract:** `GET /v1/runs/{id}/stream` is an authenticated SSE stream of project DTOs on two channels:
   - durable `run_event`s, where the SSE `id:` is the run sequence number. They are read from `run_events` after commit. On reconnect, `Last-Event-ID` resumes; if the cursor is older than retention, the server sends `snapshot_required` and the client fetches `GET /v1/runs/{id}`;
   - transient `text_delta`s keyed by `(message_id, offset)`. These are not persisted, may be lost, and are superseded by the persisted final message.
2. PostgreSQL `LISTEN/NOTIFY` (payload: run ID only) wakes stream handlers. It is a hint; correctness comes from re-reading `run_events`.
3. Commands (inputs, approve/reject, cancel) are separate `POST`s with an expected run revision. Approval is never sent over the stream and never through AG-UI/Vercel tool-approval messages.
4. AG-UI or Vercel adapters may be added later as **read-only presentation adapters** that map project DTOs. They are not a second command path.
5. Model thinking is never streamed (ADR 0004).

## Alternatives considered

- **AG-UI as the canonical contract.** It is an emerging standard with ecosystem frontends, but it would bind business records and approval to a conversation protocol. It is kept as an optional adapter.
- **WebSockets.** Bidirectional transport is not needed because commands are plain POSTs. SSE has built-in resume semantics and simpler auth and proxying.

## Consequences

- The frontend renders from project DTOs. Frontend type definitions are generated from the same schema source as the backend (MVP design §3).
- One extra adapter is needed if an AG-UI-based frontend is adopted later.

## Verification

- Reconnect test: drop the connection mid-run; there are no gaps or duplicates in durable events and no duplicate action.
- Authorization test: a stream for another tenant's run returns the same response as a non-existent run.
- Static check: no `pydantic_ai.ui` import outside an optional adapter package.
