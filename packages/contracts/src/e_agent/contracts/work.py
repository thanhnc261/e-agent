"""Host work ownership; the model cannot enqueue or claim work."""

from typing import Any, Literal

from .common import Record, UtcDatetime


class WorkClaim(Record):
    work_id: str
    tenant_id: str
    run_id: str
    kind: Literal["start", "decide", "input", "expire"]
    payload: dict[str, Any]
    owner: str
    fence: int
    lease_until: UtcDatetime
