"""Data-governance records: the model route boundary and its processing declaration (ADR 0030)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import StringConstraints

from .common import Record

DataBoundary = Annotated[
    str, StringConstraints(pattern=r"^(local|hosted:[A-Za-z0-9][A-Za-z0-9._-]*)$")
]
"""Where a model route processes data: ``local``, ``hosted:<region>`` or ``hosted:unknown``."""

BoundaryBasis = Literal["verified", "declared", "default"]
"""How the boundary is known: checked by e-agent, asserted by the operator, or assumed."""


class DataProcessing(Record):
    """The profile's declaration for a hosted route (data owner, legal basis, region)."""

    data_owner: Annotated[str, StringConstraints(min_length=1)]
    legal_basis: Annotated[str, StringConstraints(min_length=1)]
    region: Annotated[str, StringConstraints(min_length=1)]


class RouteBoundary(Record):
    boundary: DataBoundary
    basis: BoundaryBasis
