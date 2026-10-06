"""Public CRM DTOs."""

from __future__ import annotations

from e_agent.contracts.common import DecimalStr, Record
from pydantic import Field


class ContactQuery(Record):
    """Read one contact (person or company) that a lead would be about."""

    contact_ref: str


class Contact(Record):
    contact_ref: str
    name: str
    active: bool


class TeamsQuery(Record):
    """Read sales teams with their members, and the known lead sources."""


class Team(Record):
    team_ref: str
    name: str
    member_refs: tuple[str, ...]


class Source(Record):
    source_ref: str
    name: str


class Teams(Record):
    teams: tuple[Team, ...]
    sources: tuple[Source, ...]


class CreateLead(Record):
    """ERP-07 arguments: one new lead/opportunity; a repeated command never duplicates it."""

    name: str = Field(min_length=3, max_length=200)
    contact_ref: str
    team_ref: str
    owner_ref: str
    source_ref: str | None = None
    expected_revenue: DecimalStr


class LeadQuery(Record):
    operation_key: str


class LeadView(Record):
    external_ref: str
    operation_key: str
    name: str
    contact_ref: str
    team_ref: str
    owner_ref: str
    source_ref: str | None
    expected_revenue: DecimalStr
