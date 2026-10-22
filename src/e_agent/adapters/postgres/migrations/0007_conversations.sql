-- ADR 0023 §3: conversations and the run's link to one. Tenant-scoped keys, as in 0001.
-- Forward-only, no data rewrite: existing runs keep their record and belong to no conversation.

-- Ids, owner and revision only; the user's words stay in runs and run_events.
CREATE TABLE conversations (
    tenant_id        text        NOT NULL,
    conversation_id  text        NOT NULL,
    owner_id         text        NOT NULL,
    revision         integer     NOT NULL CHECK (revision >= 1),
    created_at       timestamptz NOT NULL,
    updated_at       timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, conversation_id)
);
-- An owner's conversations, newest first (`list_conversations`); ids in byte order, as the
-- in-memory store compares them.
CREATE INDEX conversations_by_owner
    ON conversations (tenant_id, owner_id, created_at DESC, conversation_id COLLATE "C" DESC);

-- NULL for a run of no conversation; the composite key keeps the link inside the tenant.
ALTER TABLE runs ADD COLUMN conversation_id text;
ALTER TABLE runs ADD CONSTRAINT runs_conversation_fk
    FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, conversation_id);
-- The column never disagrees with the run record it indexes (4c.2 review R1-4).
ALTER TABLE runs ADD CONSTRAINT runs_conversation_matches_record
    CHECK (conversation_id IS NOT DISTINCT FROM record ->> 'conversation_id');
-- A conversation's runs, oldest first. `runs` has no created_at column: the record's
-- created_at is fixed-width UTC ISO 8601 (`contracts/common.py` `_iso_utc`), so its text
-- order is time order.
CREATE INDEX runs_by_conversation
    ON runs (tenant_id, conversation_id, (record ->> 'created_at'))
    WHERE conversation_id IS NOT NULL;
