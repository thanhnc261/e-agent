"""Carried context: checked facts from earlier runs of a conversation (ADR 0023 §6-§8, D5, D6).

`carry` is pure and deterministic: it reads the earlier runs' records, events, action records
and stored evidence, never a model, a clock or a store. Per earlier run it keeps the user's
own messages (the task and each ``input.received``), the record refs the run read (the
``EvidenceRef`` of each ``read.recorded`` event's stored observation, only when the read was
``complete``) and, from each ``VERIFIED`` answer action, the argument paths whose answer
contract declares a value format and a data class, whose value passes the format and, for a
``ref``, equals a recorded source ref of the same run. Everything else is dropped, never
carried as ``personal``: model text (``message.final``, a reply, question or rationale, a
free-text answer field) and raw observations are never read.

Carried items are hints, not evidence of the new run (D6): they live only in
``_Continuation.carried``, never in ``observations`` or ``reads``, so they never become an
approved fact, an approval baseline, a staleness re-read target or a citation target.

`render_carried` writes them for the pack's ``recent_turns`` layer: every user message, value
and ref fenced as data (ADR 0032 §4), every field through the class rule of the route (ADR
0032 §5); a masked or withheld value is a ``Dropped`` entry naming it, never holding it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from e_agent.contracts import data_classes as dc
from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.capability import CapabilityDescriptor
from e_agent.contracts.context_pack import (
    ClassAction,
    Dropped,
    DroppedKind,
    DroppedReason,
    fence,
    json_text,
    masked_marker,
)
from e_agent.contracts.conversation import CarriedAnswer, CarriedRef, CarriedRun
from e_agent.contracts.digest import digest
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.evidence import Completeness, EvidenceRef
from e_agent.contracts.run import RunRecord
from e_agent.contracts.value_formats import FormatKind, ValueFormat, parse_format, value_passes

from .context_walk import Walker, _plain
from .errors import KernelError

MAX_CARRIED_RUNS = 5
"""At most this many earlier runs are carried, newest first (ADR 0023 §6)."""

CARRIED_NOTE = (
    "Facts carried from earlier runs of this conversation, newest run first. They are hints, "
    "not evidence of this run: read again before relying on one, and never cite them."
)
"""The kernel's statement at the head of the ``recent_turns`` layer (D6)."""

_INPUT = "input"


@dataclass(frozen=True)
class AnswerDeclarations:
    """What an answer contract declares for carrying: its data classes, its value formats
    and the format paths whose schema admits ``null`` (``Registry.descriptor`` and
    ``Registry.schema_document``, read by the caller so `carry` stays pure)."""

    data_classes: Mapping[str, dc.DataClass]
    formats: Mapping[str, str]
    nullable: frozenset[str] = frozenset()


def answer_declarations(
    cap: CapabilityDescriptor, document: Mapping[str, Any]
) -> AnswerDeclarations:
    """The declarations of an admitted answer capability, ``document`` its schemas."""
    schema = document.get(_INPUT)
    nullable: set[str] = set()
    for key in cap.answer_value_formats:
        tokens = dc.parse_pointer(key)
        if not isinstance(schema, Mapping) or tokens[:1] != (_INPUT,):
            continue
        for node in dc.schema_nodes(schema, tokens[1:]):
            declared = node.get("type")
            types = {declared} if isinstance(declared, str) else set(declared or ())
            if "null" in types:
                nullable.add(key)
    return AnswerDeclarations(
        data_classes=cap.data_classes,
        formats=cap.answer_value_formats,
        nullable=frozenset(nullable),
    )


# -- carry ---------------------------------------------------------------------------------
def carry(
    runs: Sequence[RunRecord],
    events_by_run: Mapping[str, Sequence[RunEvent]],
    actions_by_run: Mapping[str, Sequence[ActionRecord]],
    evidence_by_run: Mapping[str, Mapping[str, EvidenceRef]],
    declarations: Mapping[str, AnswerDeclarations],
) -> tuple[CarriedRun, ...]:
    """The carried items of a run admitted after ``runs`` (the conversation's earlier runs in
    the store's listing order, oldest first, without the admitted run): the last
    `MAX_CARRIED_RUNS`, newest first. Never sorted by ``created_at`` (ruling R2).
    ``evidence_by_run`` holds each run's stored observations' ``EvidenceRef`` by evidence id;
    ``declarations`` the answer contracts by contract id (a contract absent from it carries
    no argument)."""
    chosen = list(runs)[-MAX_CARRIED_RUNS:]
    return tuple(
        _carried_run(
            run,
            events_by_run.get(run.run_id, ()),
            actions_by_run.get(run.run_id, ()),
            evidence_by_run.get(run.run_id, {}),
            declarations,
        )
        for run in reversed(chosen)
    )


def carried_digest(carried: Sequence[CarriedRun]) -> str:
    """The ``jcs-sha256-v1`` digest of the carried items (``conversation.context_carried``)."""
    return digest([c.model_dump(mode="json") for c in carried])


def _carried_run(
    run: RunRecord,
    events: Sequence[RunEvent],
    actions: Sequence[ActionRecord],
    evidence: Mapping[str, EvidenceRef],
    declarations: Mapping[str, AnswerDeclarations],
) -> CarriedRun:
    messages = [run.task]
    refs: list[CarriedRef] = []
    for event in events:
        if event.type is RunEventType.INPUT_RECEIVED:
            text = event.payload.get("input")
            if isinstance(text, str):
                messages.append(text)
        elif event.type is RunEventType.READ_RECORDED:
            ref = _recorded_ref(event, evidence)
            if ref is not None and ref not in refs:
                refs.append(ref)
    recorded = frozenset(r.source_ref for r in refs)
    answers = []
    for action in actions:
        declared = declarations.get(action.contract_id)
        if action.state is not ActionState.VERIFIED or declared is None:
            continue
        arguments = _checked_arguments(action.arguments, declared, recorded)
        if arguments:
            answers.append(CarriedAnswer(contract_id=action.contract_id, arguments=arguments))
    return CarriedRun(
        run_id=run.run_id,
        task_id=run.task_id,
        task_version=run.task_version,
        state=run.state,
        reason_code=run.reason_code,
        user_messages=tuple(messages),
        answers=tuple(answers),
        refs=tuple(refs),
    )


def _recorded_ref(event: RunEvent, evidence: Mapping[str, EvidenceRef]) -> CarriedRef | None:
    """The ref a ``read.recorded`` event names, from the run's stored observation. None for an
    event whose evidence names no stored observation (a verifier's read, or a read a
    staleness re-read replaced) and for a read that is not ``complete`` (owner, G-A)."""
    found = evidence.get(str(event.payload.get("evidence_id")))
    contract_id = event.payload.get("contract_id")
    if found is None or found.completeness is not Completeness.COMPLETE:
        return None
    if not isinstance(contract_id, str):
        return None
    return CarriedRef(
        contract_id=contract_id,
        source_ref=found.locator,
        revision=found.revision,
        observed_at=found.observed_at,
    )


def _checked_arguments(
    arguments: Mapping[str, Any], declared: AnswerDeclarations, recorded: frozenset[str]
) -> dict[str, Any]:
    """The arguments at every declared format path that a data class covers, whose value
    passes its format (and, for a ``ref``, is a recorded source ref), nested as in
    ``arguments``. A path with an array member that fails is dropped whole, so a carried
    list is never silently shorter. Numbers become canonical decimal strings."""
    index = dc.ClassIndex(declared.data_classes)
    kept: list[dc.Path] = []
    for key in sorted(declared.formats):
        tokens = dc.parse_pointer(key)
        if tokens[:1] != (_INPUT,) or len(tokens) < 2 or index.declared(tokens) is None:
            continue
        fmt = parse_format(declared.formats[key])
        nullable = key in declared.nullable
        leaves = _leaves(arguments, tokens[1:])

        def passes(leaf: Any, fmt: ValueFormat = fmt, nullable: bool = nullable) -> bool:
            if not value_passes(fmt, leaf, nullable=nullable):
                return False
            return fmt.kind is not FormatKind.REF or leaf is None or leaf in recorded

        if leaves and all(passes(leaf) for leaf in leaves):
            kept.append(tokens[1:])
    if not kept:
        return {}
    projected: dict[str, Any] = _project(arguments, kept)
    return projected


def _leaves(value: Any, rest: Sequence[str]) -> list[Any] | None:
    """The values at ``rest`` below ``value`` (``items``: each list member); None when any
    token does not resolve. A dict key named ``items`` is never the array marker."""
    if not rest:
        return [value]
    head, tail = rest[0], rest[1:]
    if isinstance(value, list):
        if head != dc.ITEMS:
            return None
        found: list[Any] = []
        for member in value:
            below = _leaves(member, tail)
            if below is None:
                return None
            found.extend(below)
        return found
    if isinstance(value, Mapping) and head != dc.ITEMS and head in value:
        return _leaves(value[head], tail)
    return None


def _project(value: Any, paths: Sequence[dc.Path]) -> Any:
    """The part of ``value`` the kept ``paths`` reach, every number a canonical string."""
    if any(not path for path in paths):
        return _plain(value)
    if isinstance(value, list):
        below = [path[1:] for path in paths]  # every kept path names the members here
        return [_project(member, below) for member in value]
    names = sorted({path[0] for path in paths})
    return {name: _project(value[name], [p[1:] for p in paths if p[0] == name]) for name in names}


# -- render --------------------------------------------------------------------------------
ClassLookup = Callable[[str], Mapping[str, dc.DataClass]]


def render_carried(
    carried: Sequence[CarriedRun],
    rules: Mapping[dc.DataClass, ClassAction],
    index: ClassLookup,
) -> tuple[str, tuple[Dropped, ...]]:
    """The ``recent_turns`` layer text for ``carried`` (newest first) under the route's class
    rule ``rules``, and its drops. ``index`` gives an answer contract's admitted data classes;
    a contract it no longer knows classes nothing, so its values count as ``personal``. Empty
    text and no drops for no carried run."""
    if not carried:
        return "", ()
    lines = [f"carried {json_text({'note': CARRIED_NOTE})}"]
    drops: list[Dropped] = []
    for item in carried:
        lines.extend(_run_lines(item, rules, index, drops))
    return "\n".join(lines), tuple(drops)


def _run_lines(
    item: CarriedRun,
    rules: Mapping[dc.DataClass, ClassAction],
    index: ClassLookup,
    drops: list[Dropped],
) -> list[str]:
    source = f"carried:{item.run_id}"
    head = {
        "run_id": item.run_id,
        "task_id": item.task_id,
        "task_version": item.task_version,
        "state": item.state.value,
        "reason_code": None if item.reason_code is None else item.reason_code.value,
    }
    lines = [f"carried run {json_text(head)}"]
    for position, text in enumerate(item.user_messages):
        where = f"{source}#/user_messages/{position}"
        lines.extend(_text_line("  user_message", text, where, rules, drops))
    for position, answer in enumerate(item.answers):
        lines.append(f"  answer {json_text({'contract_id': answer.contract_id})}")
        lines.extend(_answer_lines(answer, position, source, rules, index, drops))
    for position, ref in enumerate(item.refs):
        meta = {"contract_id": ref.contract_id, "observed_at": ref.observed_at.isoformat()}
        lines.append(f"  ref {json_text(meta)}")
        where = f"{source}#/refs/{position}"
        texts: tuple[tuple[str, str | None], ...] = (
            ("source_ref", ref.source_ref),
            ("revision", ref.revision),
        )
        for name, value in texts:
            if value is not None:
                lines.extend(_text_line(f"    {name}", value, f"{where}/{name}", rules, drops))
    return lines


def _text_line(
    name: str,
    text: str,
    where: str,
    rules: Mapping[dc.DataClass, ClassAction],
    drops: list[Dropped],
) -> list[str]:
    """One unclassed carried text (a user message, a record ref): ``personal``, the class
    of every unmarked value (ADR 0030), fenced when the route keeps it."""
    action = rules[dc.UNMARKED_CLASS]
    if action is ClassAction.KEEP:
        return [f"{name}: {fence(text, source=where)}"]
    drops.append(Dropped(kind=DroppedKind.VALUE, ref=where, reason=DroppedReason.CLASS_ROUTE))
    if action is ClassAction.ABSENT:
        return []
    return [f"{name}: {json_text(masked_marker(dc.UNMARKED_CLASS))}"]


def _answer_lines(
    answer: CarriedAnswer,
    position: int,
    source: str,
    rules: Mapping[dc.DataClass, ClassAction],
    index: ClassLookup,
    drops: list[Dropped],
) -> list[str]:
    """An answer's carried arguments through the class walk (`Walker`) of the input side,
    one line per argument: a kept value fenced, a mask marker the walker wrote as is."""
    try:
        classes = index(answer.contract_id)
    except KernelError:  # no longer admitted: nothing is declared, so all is personal
        classes = {}
    walker = Walker(dc.ClassIndex(classes), rules, source)
    pointer = ("answers", str(position), "arguments")
    # the walker's input-side twin of `root`, which walks the output side of observations
    walked: dict[str, Any] = walker._children(dict(answer.arguments), (_INPUT,), pointer)
    drops.extend(walker.drops)
    lines = []
    for name in sorted(walked):
        value = walked[name]
        where = dc.format_pointer((*pointer, name))
        if (*pointer, name) in walker.mask_pointers or value is None:  # kernel-written
            lines.append(f"    {json_text(name)}: {json_text(value)}")
            continue
        text = value if isinstance(value, str) else json_text(value)
        lines.append(f"    {json_text(name)}: {fence(text, source=f'{source}#{where}')}")
    return lines
