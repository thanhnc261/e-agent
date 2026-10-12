"""Metadata-only plugin discovery.

Discovery reads installed distribution metadata and the packaged manifest file
without importing any plugin code (MVP design §6, step 2).
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import metadata
from importlib.machinery import PathFinder
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
    artifact_files: tuple[tuple[str, Path], ...] = ()


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
    spec = _package_spec(package_parts)
    for location in (spec.submodule_search_locations or []) if spec else []:
        candidate = Path(location) / MANIFEST_FILENAME
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise DiscoveryError(f"{dist.metadata['Name']}: missing packaged {MANIFEST_FILENAME}")


def _package_spec(parts: tuple[str, ...]):  # type: ignore[no-untyped-def]
    """Walk import paths without executing any parent package."""
    search = sys.path
    spec = None
    for index in range(len(parts)):
        spec = PathFinder.find_spec(".".join(parts[: index + 1]), search)
        if spec is None:
            return None
        search = list(spec.submodule_search_locations or ())
    return spec


def artifact_files(dist: metadata.Distribution, entry_value: str) -> tuple[tuple[str, Path], ...]:
    """Inventory package resources and executable parent packages without importing."""
    package = tuple(_manifest_package(entry_value).split("."))
    result: dict[str, Path] = {}
    for item in dist.files or ():
        if item.parts[: len(package)] == package and "__pycache__" not in item.parts:
            result[str(item)] = Path(str(dist.locate_file(item)))
    roots = {
        path.parents[len(Path(name).parts) - len(package) - 1] for name, path in result.items()
    }
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                result["/".join(package) + "/" + path.relative_to(root).as_posix()] = path
    if not result:
        spec = _package_spec(package)
        for location in (spec.submodule_search_locations or ()) if spec else ():
            root = Path(location)
            for path in root.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    result["/".join(package) + "/" + path.relative_to(root).as_posix()] = path
    for index in range(1, len(package)):
        spec = _package_spec(package[:index])
        if spec and spec.origin and spec.origin != "namespace":
            result["/".join(package[:index]) + "/__init__.py"] = Path(spec.origin)
    return tuple(sorted(result.items()))


def artifact_digest(files: tuple[tuple[str, Path], ...]) -> str:
    """Compare these bytes with an independently approved build inventory digest."""
    inventory = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files}
    if not inventory:
        raise DiscoveryError("plugin has no artifact inventory")
    raw = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


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
                    artifact_files=artifact_files(dist, ep.value),
                )
            )
    return found
