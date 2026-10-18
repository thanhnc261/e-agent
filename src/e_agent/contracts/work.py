"""Host work ownership; the model cannot enqueue or claim work."""

from typing import Any, Literal

from .common import Record, UtcDatetime


class WorkClaim(Record):
    work_id: str
    tenant_id: str
    run_id: str
    kind: Literal["start", "decide", "input", "expire", "resume"]
    """``resume`` continues a multi-step plan after a crash, under the claim (ADR 0025)."""
    payload: dict[str, Any]
    owner: str
    fence: int
    lease_until: UtcDatetime
