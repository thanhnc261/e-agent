"""Generate an artifact pin from a trusted wheel build, without importing its code.

Record the returned artifact_sha256 in the non-secret live profile. Generating
an inventory from an untrusted installed directory does not establish trust.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile


def inventory(wheel: Path) -> dict[str, object]:
    with ZipFile(wheel) as archive:
        manifests = [n for n in archive.namelist() if n.endswith("/e_agent_plugin.json")]
        if len(manifests) != 1:
            raise ValueError("wheel must contain exactly one plugin manifest")
        name = manifests[0]
        root = name.rsplit("/", 1)[0] + "/"
        files = {
            n: hashlib.sha256(archive.read(n)).hexdigest()
            for n in archive.namelist()
            if n.startswith(root) and not n.endswith("/")
        }
        parts = root.rstrip("/").split("/")
        for index in range(1, len(parts)):
            parent = "/".join(parts[:index]) + "/__init__.py"
            if parent in archive.namelist():
                files[parent] = hashlib.sha256(archive.read(parent)).hexdigest()
        manifest = json.loads(archive.read(name))
        raw = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return {
            "plugin_id": manifest["plugin_id"],
            "version": manifest["version"],
            "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "manifest_sha256": hashlib.sha256(archive.read(name)).hexdigest(),
            "artifact_sha256": hashlib.sha256(raw).hexdigest(),
            "files": files,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    sys.stdout.write(json.dumps(inventory(args.wheel), indent=2) + "\n")


if __name__ == "__main__":
    main()
