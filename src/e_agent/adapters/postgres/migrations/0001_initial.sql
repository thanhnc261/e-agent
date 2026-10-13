-- e-agent ledger schema v1. Every reference is tenant-scoped (composite keys)
-- so a row can never point at another tenant's run or action.

CREATE TABLE runs (
    tenant_id   text        NOT NULL,
    run_id      text        NOT NULL,
    state       text        NOT NULL,
    revision    integer     NOT NULL CHECK (revision >= 1),
    record      jsonb       NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, run_id)
);
CREATE INDEX runs_unfinished ON runs (state)
    WHERE state NOT IN ('SUCCEEDED', 'FAILED', 'CANCELLED');

CREATE TABLE run_events (
    event_id    text        PRIMARY KEY,
    tenant_id   text        NOT NULL,
    run_id      text        NOT NULL,
    sequence    integer     NOT NULL CHECK (sequence >= 1),
    type        text        NOT NULL,
    action_id   text,
    record      jsonb       NOT NULL,
    UNIQUE (tenant_id, run_id, sequence),
    FOREIGN KEY (tenant_id, run_id) REFERENCES runs (tenant_id, run_id)
);

CREATE TABLE actions (
    tenant_id             text    NOT NULL,
    action_id             text    NOT NULL,
    run_id                text    NOT NULL,
    logical_operation_id  text    NOT NULL,
    connection_id         text    NOT NULL,
    state                 text    NOT NULL,
    revision              integer NOT NULL CHECK (revision >= 1),
    record                jsonb   NOT NULL,
    PRIMARY KEY (tenant_id, action_id),
    FOREIGN KEY (tenant_id, run_id) REFERENCES runs (tenant_id, run_id)
);
CREATE INDEX actions_by_run ON actions (tenant_id, run_id);

-- One admitted reservation per intended operation (MVP design §9).
CREATE TABLE operation_reservations (
    tenant_id             text        NOT NULL,
    connection_id         text        NOT NULL,
    logical_operation_id  text        NOT NULL,
    action_id             text        NOT NULL,
    reserved_at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, connection_id, logical_operation_id),
    FOREIGN KEY (tenant_id, action_id) REFERENCES actions (tenant_id, action_id)
);

CREATE TABLE approvals (
    tenant_id    text  NOT NULL,
    approval_id  text  NOT NULL,
    action_id    text  NOT NULL,
    record       jsonb NOT NULL,
    PRIMARY KEY (tenant_id, approval_id),
    FOREIGN KEY (tenant_id, action_id) REFERENCES actions (tenant_id, action_id)
);

CREATE TABLE receipts (
    id         bigserial PRIMARY KEY,
    tenant_id  text      NOT NULL,
    action_id  text      NOT NULL,
    record     jsonb     NOT NULL,
    FOREIGN KEY (tenant_id, action_id) REFERENCES actions (tenant_id, action_id)
);

CREATE TABLE outcome_reports (
    id         bigserial PRIMARY KEY,
    tenant_id  text      NOT NULL,
    run_id     text      NOT NULL,
    action_id  text,
    record     jsonb     NOT NULL,
    FOREIGN KEY (tenant_id, run_id) REFERENCES runs (tenant_id, run_id)
);

-- Kernel continuation and opaque driver state (redacted; no secrets, no reasoning).
CREATE TABLE continuations (
    tenant_id     text        NOT NULL,
    run_id        text        NOT NULL,
    state         jsonb       NOT NULL,
    driver_state  jsonb,
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, run_id),
    FOREIGN KEY (tenant_id, run_id) REFERENCES runs (tenant_id, run_id)
);
