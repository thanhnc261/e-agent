-- A runnable host command, with one active owner per run. No provider transaction.
CREATE TABLE run_work (
    work_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    run_id text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('start', 'decide', 'input')),
    request_digest text NOT NULL,
    payload jsonb NOT NULL,
    state text NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING', 'CLAIMED', 'DONE')),
    owner text,
    fence bigint NOT NULL DEFAULT 0,
    lease_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, run_id, kind, request_digest)
);
CREATE INDEX run_work_runnable ON run_work (state, lease_until, created_at);
