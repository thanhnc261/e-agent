-- API request idempotency (MVP design §9): same actor + key + payload returns the
-- existing run; same key with a different payload is a conflict.
CREATE TABLE api_idempotency (
    tenant_id       text        NOT NULL,
    actor_id        text        NOT NULL,
    idem_key        text        NOT NULL,
    request_digest  text        NOT NULL,
    run_id          text        NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, actor_id, idem_key)
);
