"""Write the API's OpenAPI document (source of the generated TypeScript types).

uv run python scripts/export_openapi.py            # write
uv run python scripts/export_openapi.py --check    # CI: fail if it is out of date
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from e_agent.server.api import create_app

TARGET = Path(__file__).resolve().parent.parent / "ui/packages/client/openapi.json"


async def _never() -> None:  # the schema needs no runtime
    raise RuntimeError


def main() -> int:
    app = create_app(_never)  # type: ignore[arg-type]
    text = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        if not TARGET.exists() or TARGET.read_text("utf-8") != text:
            sys.stderr.write("openapi.json is out of date: run scripts/export_openapi.py\n")
            return 1
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
