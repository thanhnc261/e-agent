#!/usr/bin/env bash
# Run a throwaway Odoo 19 sandbox from source for e-agent integration tests
# (used by the dev container and the nightly CI job; the owner's machine uses
# the odoo19-learning Docker stack instead, see docs/runbooks/i06-odoo-bridge.md).
#
#   PGHOST/PGPORT/PGUSER/PGPASSWORD must point at a PostgreSQL where PGUSER can CREATEDB.
#   ODOO_KEYS_FILE (required): private path where the sandbox API keys are written.
#   ODOO_SRC (default /opt/odoo-src/odoo), ODOO_VENV (default /opt/odoo-venv), DB (e_agent_odoo)
set -euo pipefail
: "${ODOO_KEYS_FILE:?set ODOO_KEYS_FILE to a private path for the sandbox API keys}"
ODOO_SRC=${ODOO_SRC:-/opt/odoo-src/odoo}
ODOO_VENV=${ODOO_VENV:-/opt/odoo-venv}
DB=${DB:-e_agent_odoo}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
if [ ! -d "$ODOO_SRC" ]; then
  git clone -q --depth 1 -b 19.0 https://github.com/odoo/odoo.git "$ODOO_SRC"
fi
if [ ! -x "$ODOO_VENV/bin/python" ]; then
  uv venv -q --python 3.12 "$ODOO_VENV"
  grep -v -i "python-ldap\|^#" "$ODOO_SRC/requirements.txt" \
    | sed -E 's/^psycopg2==([^ ;]+)/psycopg2-binary/' > /tmp/odoo-req.txt
  uv pip install -q --python "$ODOO_VENV/bin/python" -r /tmp/odoo-req.txt
fi
COMMON=(-d "$DB" --db_host "${PGHOST:-127.0.0.1}" --db_port "${PGPORT:-5432}" \
  --db_user "${PGUSER:-odoo}" --db_password "${PGPASSWORD:-odoo}" \
  --addons-path="$ODOO_SRC/addons,$REPO/addons")
"$ODOO_VENV/bin/python" "$ODOO_SRC/odoo-bin" "${COMMON[@]}" -i e_agent_bridge \
  --stop-after-init --log-level=warn
"$ODOO_VENV/bin/python" "$ODOO_SRC/odoo-bin" shell "${COMMON[@]}" --log-level=warn \
  < "$REPO/scripts/dev/odoo_test_users.py"
exec "$ODOO_VENV/bin/python" "$ODOO_SRC/odoo-bin" "${COMMON[@]}" --http-port 8069 \
  --http-interface 127.0.0.1 --db-filter "^$DB\$" --workers 0 --log-level=warn
