# ruff: noqa: F821
# Run inside `odoo-bin shell` against a SANDBOX database only. Sets the sandbox
# marker, creates the e-agent integration user, and writes 7-day API keys for the
# integration user and the admin to ODOO_KEYS_FILE (mode 0600). Never commit keys.
import datetime
import json
import os

env = self.env
env["ir.config_parameter"].sudo().set_param("e_agent.sandbox_marker", "e-agent-ci-sandbox")
group = env.ref("e_agent_bridge.group_e_agent_integration")
rights = [
    group.id,
    env.ref("base.group_user").id,
    env.ref("purchase.group_purchase_user").id,
    env.ref("stock.group_stock_user").id,
]
user = env["res.users"].search([("login", "=", "e-agent-integration")])
if not user:
    user = env["res.users"].create(
        {
            "name": "e-agent integration",
            "login": "e-agent-integration",
            "group_ids": [(6, 0, rights)],
        }
    )
admin = env.ref("base.user_admin")
admin.write({"group_ids": [(4, group.id)]})
expires = datetime.datetime.now() + datetime.timedelta(days=7)
keys = {
    name: env["res.users.apikeys"].with_user(u)._generate(None, f"e-agent {name}", expires)
    for u, name in ((user, "integration"), (admin, "admin"))
}
env.cr.commit()
path = os.environ["ODOO_KEYS_FILE"]  # required: a private path chosen by the caller
with open(path, "w") as fh:
    json.dump(keys, fh)
os.chmod(path, 0o600)
print("KEYS-WRITTEN", sorted(keys))
