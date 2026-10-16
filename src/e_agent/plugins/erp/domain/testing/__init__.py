"""Deterministic fixtures for the walking skeleton and tests.

Everything here is a FIXTURE: a scripted (non-model) driver and a
non-authoritative rule checker. The fake ERP is the separate simulator plugin
``fixture-erp`` (``e_agent.plugins.erp.simulator``). Evidence produced with them is labelled
``environment=fixture`` and is never a capability claim (AGENTS.md).
"""
