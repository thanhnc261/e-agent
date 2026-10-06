"""Portable e-agent wire records.

Contracts contain only generic, provider-neutral records. Domain-specific fields
belong to domain APIs; vendor, framework and ORM types never appear here.
"""

CONTRACTS_SCHEMA_VERSION = "1"

__all__ = ["CONTRACTS_SCHEMA_VERSION"]
