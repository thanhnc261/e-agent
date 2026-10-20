"""The context assembler's value walker (ADR 0030, ADR 0032 §3): classes each value of one
observation through the capability's declarations and the route's class rule, then bounds
the rendering. Pure, like ``context.assemble``: it reads its arguments only.

A dict key named ``items`` is ambiguous: ADR 0030's class keys write ``items`` for every
array member, so a declaration beneath the marker may name it. Most restrictive wins: its
subtree is walked under the marker's tokens and floored at the unmarked class (``personal``),
so a ``secret`` declared beneath is still removed and a ``public`` one is raised to
``personal``. On a route that does not keep ``personal`` the entry is left out with its key,
as any key that may be data is (D3-12, D3-81)."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from decimal import Decimal
from typing import Any

from e_agent.contracts import data_classes as dc
from e_agent.contracts.context_pack import (
    ClassAction,
    Dropped,
    DroppedKind,
    DroppedReason,
    json_text,
    masked_marker,
    number_text,
)

from .errors import ErrorCode, KernelError

KEEP = ClassAction.KEEP
_RANK = dc.RESTRICTIVENESS.index


def _plain(value: Any) -> Any:
    """A JSON value with every number as its canonical decimal string."""
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int | float | Decimal):
        return number_text(value)
    if isinstance(value, Mapping):
        return {_key(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    raise KernelError(ErrorCode.INVALID_REQUEST, "observation data holds a value outside JSON")


def _key(key: Any) -> str:
    if not isinstance(key, str):
        raise KernelError(ErrorCode.INVALID_REQUEST, "observation data has a non-string key")
    return key


Pointer = tuple[str, ...]


class Walker:
    """Renders one observation's data through its class declarations and the route's row,
    then bounds it. Pointers in drops are into the original data."""

    def __init__(
        self, index: dc.ClassIndex, rules: Mapping[dc.DataClass, ClassAction], evidence_id: str
    ) -> None:
        self.index, self.rules, self.evidence_id = index, rules, evidence_id
        self.drops: list[Dropped] = []
        self.masked = False
        self.mask_pointers: set[Pointer] = set()
        """Where the kernel wrote a mask marker; a provider string never poses as one."""
        self.positions: dict[int, list[int]] = {}
        """Original indices of each rendered list, by the list's id."""

    def ref(self, pointer: Sequence[str]) -> str:
        return f"{self.evidence_id}#{dc.format_pointer(pointer)}"

    def _drop(self, kind: DroppedKind, pointer: Sequence[str], reason: DroppedReason) -> None:
        self.drops.append(Dropped(kind=kind, ref=self.ref(pointer), reason=reason))

    # rendering ----------------------------------------------------------------------
    def root(self, data: Mapping[str, Any]) -> dict[str, Any]:
        rendered: dict[str, Any] = self._children(data, ("output",), ())
        return rendered

    def _node(
        self, value: Any, tokens: dc.Path, pointer: Pointer, floor: dc.DataClass | None = None
    ) -> tuple[bool, Any]:
        """``floor`` is a class every value here is at least (most restrictive wins)."""
        declared = self.index.declared(tokens)
        if floor is not None:
            declared = floor if declared is None else max(declared, floor, key=_RANK)
        if isinstance(value, Mapping | list | tuple) and self.index.declared_below(tokens):
            action = KEEP if declared is None else self.rules[declared]
            if action is KEEP:
                return True, self._children(value, tokens, pointer, floor)
        # a leaf, or a container no declaration reaches into: one value of one class, so
        # an undeclared dict's keys are masked with it (ADR 0030)
        data_class = dc.UNMARKED_CLASS if declared is None else declared
        action = self.rules[data_class]
        if action is KEEP:
            return True, self._track(_plain(value))
        self._drop(DroppedKind.VALUE, pointer, DroppedReason.CLASS_ROUTE)
        self.masked = True  # a removed secret too: the rendering is not the whole (D3-11)
        if action is ClassAction.ABSENT:
            return False, None
        self.mask_pointers.add(pointer)
        return True, masked_marker(data_class)

    def _children(
        self, value: Any, tokens: dc.Path, pointer: Pointer, floor: dc.DataClass | None = None
    ) -> Any:
        keeps_unmarked = self.rules[dc.UNMARKED_CLASS] is KEEP
        if isinstance(value, Mapping):
            out: dict[str, Any] = {}
            unnamed = False
            for key, item in value.items():
                name = _key(key)
                child, child_floor = (*tokens, name), floor  # numeric or not, a key is itself
                if name == dc.ITEMS:  # the array marker's token: see the module docstring
                    child_floor = dc.UNMARKED_CLASS
                if (name == dc.ITEMS or not self.index.named(child)) and not keeps_unmarked:
                    unnamed = True  # the key may be data: the entry is left out (D3-12)
                    continue
                kept, rendered = self._node(item, child, (*pointer, name), child_floor)
                if kept:
                    out[name] = rendered
            if unnamed:  # one drop naming the parent, never the key
                self.masked = True
                self._drop(DroppedKind.VALUE, pointer, DroppedReason.CLASS_ROUTE)
            return out
        members: list[Any] = []
        positions: list[int] = []
        for index, item in enumerate(value):
            kept, rendered = self._node(item, (*tokens, dc.ITEMS), (*pointer, str(index)), floor)
            if kept:
                members.append(rendered)
                positions.append(index)
        self.positions[id(members)] = positions
        return members

    def _track(self, value: Any) -> Any:
        """Record the original indices of every list in a value rendered whole."""
        if isinstance(value, list):
            self.positions[id(value)] = list(range(len(value)))
            for item in value:
                self._track(item)
        elif isinstance(value, dict):
            for item in value.values():
                self._track(item)
        return value

    # bounding -----------------------------------------------------------------------
    def _lists(self, value: Any, pointer: Pointer) -> Iterator[tuple[Pointer, list[Any]]]:
        """Every non-empty list in document order, with its original pointer."""
        if isinstance(value, dict):
            for key, item in value.items():
                yield from self._lists(item, (*pointer, key))
        elif isinstance(value, list):
            if value:
                yield pointer, value
            positions = self.positions[id(value)]
            for index, item in enumerate(value):
                yield from self._lists(item, (*pointer, str(positions[index])))

    def _strings(self, value: Any, pointer: Pointer) -> Iterator[tuple[Pointer, Any, Any]]:
        """Every cuttable string as (original pointer, parent, key), in document order."""
        if isinstance(value, dict):
            entries = [(key, item, key) for key, item in value.items()]
        elif isinstance(value, list):
            positions = self.positions[id(value)]
            entries = [(i, item, str(positions[i])) for i, item in enumerate(value)]
        else:
            return
        for key, item, token in entries:
            if isinstance(item, str) and item and (*pointer, token) not in self.mask_pointers:
                yield (*pointer, token), value, key
            else:
                yield from self._strings(item, (*pointer, token))

    def bound(
        self, data: dict[str, Any], size: Callable[[dict[str, Any]], int], limit: int
    ) -> bool:
        """Cut ``data`` in place to ``limit`` bytes of tool return: list members from the end
        (the longest list first, the first in document order on a tie), then long strings
        at their end. Each removed member and each cut string is a ``bound`` drop. False
        when nothing is left to cut and it still does not fit."""
        cut: set[str] = set()
        current = size(data)
        while current > limit:
            if lists := sorted(self._lists(data, ()), key=lambda found: -len(found[1])):
                pointer, target = lists[0]
                runner_up = len(lists[1][1]) if len(lists) > 1 else 0
                while True:  # one member per round at least, so equal lists alternate
                    member = target.pop()
                    original = self.positions[id(target)].pop()
                    self._drop(DroppedKind.ITEM, (*pointer, str(original)), DroppedReason.BOUND)
                    current -= len(json_text(member).encode("utf-8")) + (1 if target else 0)
                    if current <= limit or len(target) <= runner_up:
                        break
                if current <= limit:
                    current = size(data)  # the accounting is exact; confirm it anyway
                continue
            strings = list(self._strings(data, ()))
            if not strings:
                return False
            pointer, parent, key = max(strings, key=lambda found: len(found[1][found[2]]))
            text: str = parent[key]
            parent[key] = text[: max(0, len(text) - max(current - limit, 1))]
            if self.ref(pointer) not in cut:
                cut.add(self.ref(pointer))
                self._drop(DroppedKind.VALUE, pointer, DroppedReason.BOUND)
            current = size(data)
        return True
