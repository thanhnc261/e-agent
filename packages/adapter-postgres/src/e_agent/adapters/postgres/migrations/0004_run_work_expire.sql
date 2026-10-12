-- ADR 0019: approval expiry runs as fenced work, never outside a claim.
ALTER TABLE run_work DROP CONSTRAINT run_work_kind_check;
ALTER TABLE run_work ADD CONSTRAINT run_work_kind_check
    CHECK (kind IN ('start', 'decide', 'input', 'expire'));
