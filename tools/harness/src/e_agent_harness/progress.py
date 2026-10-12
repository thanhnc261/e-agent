"""Append-only progress log (harness plan H1, principle P1).

Format, one entry per session checkpoint::

    ## <ISO timestamp> · <session> · <task>
    - changed: <what changed>
    - next: <the one next action>
    - open: <open items, or "none">
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

HEADER = "# Progress log\n"
ENTRY_RE = re.compile(r"^## (\S+) · (\S+) · (\S+)\s*$", re.M)
FIELD_RE = re.compile(r"^- (changed|next|open): (.*)$")


class ProgressEntry(NamedTuple):
    timestamp: str
    session: str
    task: str
    changed: str
    next: str
    open: str

    def to_dict(self) -> dict[str, str]:
        return dict(self._asdict())

    def render(self) -> str:
        return (
            f"## {self.timestamp} · {self.session} · {self.task}\n"
            f"- changed: {self.changed}\n"
            f"- next: {self.next}\n"
            f"- open: {self.open}\n"
        )


def parse_progress(text: str) -> list[ProgressEntry]:
    entries: list[ProgressEntry] = []
    matches = list(ENTRY_RE.finditer(text))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        fields = {"changed": "", "next": "", "open": "none"}
        for line in text[match.end() : end].splitlines():
            field = FIELD_RE.match(line.strip())
            if field:
                fields[field.group(1)] = field.group(2).strip()
        entries.append(ProgressEntry(match.group(1), match.group(2), match.group(3), **fields))
    return entries


def append_entry(path: Path, entry: ProgressEntry) -> None:
    exists = path.is_file()
    with path.open("a", encoding="utf-8") as fh:
        if not exists:
            fh.write(HEADER)
        fh.write("\n" + entry.render())
