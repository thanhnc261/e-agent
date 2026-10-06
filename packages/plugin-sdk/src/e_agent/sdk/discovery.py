"""Metadata-only plugin discovery.

Discovery reads installed distribution metadata and the packaged manifest file
without importing any plugin code (MVP design §6, step 2).
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from . import ENTRY_POINT_GROUP, MANIFEST_FILENAME
from .manifest import PluginManifest


class DiscoveryError(Exception):
    pass


@dataclass(frozen=True)
class DiscoveredPlugin:
    entry_point_name: str
    entry_point_value: str
    distribution: str
    distribution_version: str
    manifest: PluginManifest
    manifest_text: str


def _manifest_package(entry_value: str) -> str:
    """The manifest lives in the package that contains the factory module."""
    module = entry_value.split(":", 1)[0]
    return module.rpartition(".")[0] or module


def _read_manifest(dist: metadata.Distribution, entry_value: str) -> str:
    package_parts = tuple(_manifest_package(entry_value).split("."))
    # 1. Installed wheels list their files in RECORD: read without any import.
    for file in dist.files or ():
        if file.parts[:-1] == package_parts and file.parts[-1] == MANIFEST_FILENAME:
            text = file.read_text(encoding="utf-8")
            if text is not None:
                return text
    # 2. Editable installs only record a .pth file: locate the package directory
    #    with find_spec, which does not execute the plugin package itself (only
    #    namespace parents such as ``e_agent``, which contain no code).
    spec = importlib.util.find_spec(".".join(package_parts))
    for location in (spec.submodule_search_locations or []) if spec else []:
        candidate = Path(location) / MANIFEST_FILENAME
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise DiscoveryError(f"{dist.metadata['Name']}: missing packaged {MANIFEST_FILENAME}")


def discover(paths: Iterable[str] | None = None) -> list[DiscoveredPlugin]:
    """List plugins in ``paths`` (default: sys.path) without importing them."""
    found: list[DiscoveredPlugin] = []
    dists = (
        metadata.distributions(path=list(paths)) if paths is not None else metadata.distributions()
    )
    seen: set[str] = set()
    for dist in dists:
        name = dist.metadata["Name"]
        if name in seen:
            continue
        seen.add(name)
        for ep in dist.entry_points:
            if ep.group != ENTRY_POINT_GROUP:
                continue
            text = _read_manifest(dist, ep.value)
            try:
                manifest = PluginManifest.model_validate(json.loads(text))
            except ValueError as exc:
                raise DiscoveryError(f"{name}: invalid manifest: {exc}") from exc
            found.append(
                DiscoveredPlugin(
                    entry_point_name=ep.name,
                    entry_point_value=ep.value,
                    distribution=name,
                    distribution_version=dist.version,
                    manifest=manifest,
                    manifest_text=text,
                )
            )
    return found
