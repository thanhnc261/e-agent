"""Trusted identity and task context established by the host, never by the model."""

from __future__ import annotations

from .common import Record, UtcDatetime


class Principal(Record):
    principal_id: str
    tenant_id: str
    roles: frozenset[str]
    display_name: str | None = None


class Budgets(Record):
    max_driver_turns: int = 12
    max_read_calls: int = 20
    max_validation_repairs: int = 2
    max_admitted_writes: int = 1


class TaskContext(Record):
    run_id: str
    tenant_id: str
    principal: Principal
    resource_scope: frozenset[str]
    deadline: UtcDatetime | None = None
    budgets: Budgets = Budgets()
