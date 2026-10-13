"""Public receivables DTOs. Read-only: nothing here can post, pay or write off."""

from __future__ import annotations

from datetime import date

from e_agent.contracts.common import DecimalStr, Record


class OpenInvoicesQuery(Record):
    """Read posted customer invoices with an open residual amount."""

    as_of: date


class OpenInvoice(Record):
    invoice_ref: str
    external_ref: str
    customer_ref: str
    due_date: date
    residual: DecimalStr
    currency: str


class OpenInvoices(Record):
    as_of: date
    company: str
    invoices: tuple[OpenInvoice, ...]


class CurrencyTotal(Record):
    currency: str
    total: DecimalStr


class OverdueInvoicesAnswer(Record):
    """ERP-08 answer: invoices due before ``as_of`` with residual > 0, totals per currency."""

    as_of: date
    overdue_invoice_refs: tuple[str, ...]
    totals: tuple[CurrencyTotal, ...]
    summary: str
