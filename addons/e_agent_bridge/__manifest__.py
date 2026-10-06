{
    "name": "e-agent bridge",
    "version": "19.0.0.2.0",
    "summary": "Narrow, transactional commands for the e-agent action gateway (ADR 0005)",
    "description": """
Each public bridge command reserves an operation key, validates draft-only
preconditions and performs the business change in ONE JSON-2 call, so the
ledger row and the business record commit together. Reads are narrow,
company-scoped and read-only. Sandbox seeding refuses to run without the
e_agent.sandbox_marker system parameter.
    """,
    "license": "LGPL-3",
    "author": "e-agent",
    "depends": ["purchase_stock", "sale_stock", "crm"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
}
