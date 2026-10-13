"""Public text streaming: the per-run public text bus (Phase 1 split of api.py)."""

from __future__ import annotations

from e_agent.contracts.common import new_id
from e_agent.contracts.context import TaskContext
from pydantic import BaseModel


class TextFrame(BaseModel):
    message_id: str
    stream_id: str
    offset: int
    text: str
    reset: bool


class PublicTextBus:
    """Bounded process memory; never writes public token fragments to the ledger."""

    def __init__(self) -> None:
        self.stream_id = new_id("text_stream")
        self.frames: dict[tuple[str, str], list[TextFrame]] = {}
        self.prefixes: dict[tuple[str, str], str] = {}
        self.messages: dict[tuple[str, str], str] = {}
        self.last_offsets: dict[tuple[str, str], int] = {}

    def discard(self, tenant_id: str, run_id: str) -> None:
        """Drop buffered text once the kernel has recorded it as a question or reply.

        Offsets keep counting so a connected client never sees a rewind."""
        key = (tenant_id, run_id)
        if key not in self.frames:
            return
        frames = self.frames[key]
        if frames:
            self.last_offsets[key] = frames[-1].offset
        self.frames[key] = []
        self.prefixes.pop(key, None)
        self.messages.pop(key, None)

    async def emit(self, ctx: TaskContext, text: str, *, new_message: bool = False) -> None:
        key = (ctx.tenant_id, ctx.run_id)
        if key not in self.frames and len(self.frames) >= 128:
            oldest = next(iter(self.frames))
            self.frames.pop(oldest)
            self.prefixes.pop(oldest, None)
            self.messages.pop(oldest, None)
            self.last_offsets.pop(oldest, None)
        frames = self.frames.setdefault(key, [])
        if new_message or key not in self.messages:
            self.messages[key] = new_id("message")
        prefix = "" if new_message else self.prefixes.get(key, "")
        text = text[: max(0, 32000 - len(prefix))]
        if not text:
            return
        offset = frames[-1].offset + 1 if frames else self.last_offsets.get(key, 0) + 1
        frames.append(
            TextFrame(
                message_id=self.messages[key],
                stream_id=self.stream_id,
                offset=offset,
                text=text,
                reset=new_message,
            )
        )
        self.frames[key] = frames[-128:]
        self.prefixes[key] = prefix + text

    def snapshot(self, tenant_id: str, run_id: str) -> TextFrame | None:
        key = (tenant_id, run_id)
        frames = self.frames.get(key, [])
        if not frames:
            return None
        return TextFrame(
            message_id=self.messages[key],
            stream_id=self.stream_id,
            offset=frames[-1].offset,
            text=self.prefixes[key],
            reset=True,
        )

    def after(self, tenant_id: str, run_id: str, offset: int) -> list[TextFrame]:
        frames = self.frames.get((tenant_id, run_id), [])
        if frames and offset < frames[0].offset - 1:
            snapshot = self.snapshot(tenant_id, run_id)
            return [snapshot] if snapshot else []
        return [frame for frame in frames if frame.offset > offset]
