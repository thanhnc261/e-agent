-- ADR 0025 amendment: a plan resumes after a crash only as fenced work, never in recovery.
ALTER TABLE run_work DROP CONSTRAINT run_work_kind_check;
ALTER TABLE run_work ADD CONSTRAINT run_work_kind_check
    CHECK (kind IN ('start', 'decide', 'input', 'expire', 'resume'));
