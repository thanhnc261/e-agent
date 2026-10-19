-- ADR 0025: action plans and step records. Tenant-scoped keys, as in 0001.

-- A plan is stored once and never overwritten; `record` holds its wire form, with each
-- lineage placeholder as {"$lineage": {"step", "path"}}.
CREATE TABLE action_plans (
    tenant_id   text        NOT NULL,
    plan_id     text        NOT NULL,
    run_id      text        NOT NULL,
    record      jsonb       NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, plan_id),
    FOREIGN KEY (tenant_id, run_id) REFERENCES runs (tenant_id, run_id)
);
CREATE INDEX action_plans_by_run ON action_plans (tenant_id, run_id);

-- Append-only step state rows: a status change is a new row with a higher sequence.
CREATE TABLE run_steps (
    tenant_id   text    NOT NULL,
    run_id      text    NOT NULL,
    sequence    integer NOT NULL CHECK (sequence >= 0),
    step_id     text    NOT NULL,
    kind        text    NOT NULL,
    status      text    NOT NULL,
    action_id   text,
    record      jsonb   NOT NULL,
    PRIMARY KEY (tenant_id, run_id, sequence),
    FOREIGN KEY (tenant_id, run_id) REFERENCES runs (tenant_id, run_id)
);

-- Rows written before this migration keep NULL: they belong to no plan.
ALTER TABLE actions ADD COLUMN plan_id text;
ALTER TABLE actions ADD COLUMN step_index integer CHECK (step_index >= 0);
ALTER TABLE actions ADD CONSTRAINT actions_plan_step_together
    CHECK ((plan_id IS NULL) = (step_index IS NULL));
