"""Public inventory DTOs."""

from __future__ import annotations

from e_agent.contracts.common import DecimalStr, Record


class AvailabilityQuery(Record):
    """Read available and inbound stock for one product."""

    product_ref: str


class Availability(Record):
    product_ref: str
    available: DecimalStr
    inbound: DecimalStr
    unit: str
