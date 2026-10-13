"""Hatch build hook shared by every e-agent distribution (Phase 1 layout).

A standard wheel gets its package sub-tree from the shared src/ tree. An
editable install gets only the .pth that dev-mode-dirs writes: a static
force-include would also be copied into site-packages and shadow src/.
The distributions are released as wheels; an sdist could not carry the
shared tree, so building one fails instead of producing an empty archive.
"""

from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class SrcTreeHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name == "sdist":
            raise RuntimeError(
                "e-agent distributions build as wheels from the shared src/ tree; "
                "use `uv build --package <name> --wheel`"
            )
        if version != "standard":
            return
        package = self.config["package"]
        source = Path(self.root, "../../src", package).resolve()
        if not source.is_dir():
            raise ValueError(f"missing package source: {source}")
        build_data["force_include"][str(source)] = package
