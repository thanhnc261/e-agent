"""`feature.fallback`: a feature in `on` mode returns to the existing path (ADR 0027).

The helper only records the event; the run keeps its state, because a fallback code never
ends a run (ADR 0025). The event carries the code and its fixed message, never caller text
(PR-25, PR-28). Runs over both stores through the `run_store` fixture (ENG-STORE-1).
"""

import ast
import inspect
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import Features
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.evidence import (
    BLOCKED_BY_DESIGN,
    INFRASTRUCTURE_OR_BUDGET,
    build_evidence,
    classify,
)
from e_agent.kernel.features import FALLBACK_FEATURES, FALLBACK_MESSAGES, TERMINAL_MESSAGES

from .conftest import TENANT, Kernel

MakeKernel = Callable[..., Kernel]

FALLBACK_CODES = (
    ReasonCode.IR_TASK_UNRESOLVED,
    ReasonCode.IR_COMPILE_FAILED,
    ReasonCode.IR_VALIDATION_FAILED,
    # Phase 3 (ADR 0031, ADR 0032, ADR 0033)
    ReasonCode.CONTEXT_ASSEMBLY_FAILED,
    ReasonCode.REPEAT_CHECK_FAILED,
    ReasonCode.GROUNDING_CHECK_FAILED,
)
NOT_FALLBACK_CODES = tuple(c for c in ReasonCode if c not in FALLBACK_CODES)
PHASE3_TERMINAL = {
    ReasonCode.CONTEXT_UNAVAILABLE: INFRASTRUCTURE_OR_BUDGET,
    ReasonCode.REPEAT_UNAVAILABLE: INFRASTRUCTURE_OR_BUDGET,
    ReasonCode.GROUNDING_UNAVAILABLE: INFRASTRUCTURE_OR_BUDGET,
    ReasonCode.DRIVER_STATE_MISMATCH: None,  # `failed`
    ReasonCode.ROUTE_BOUNDARY_UNMET: BLOCKED_BY_DESIGN,
}
"""The terminal codes Task 3b.2 adds, by their ``classify`` group (ADR 0032 §11)."""
KERNEL = Path(__file__).resolve().parents[3] / "src/e_agent/kernel"


async def _start(k: Kernel):  # type: ignore[no-untyped-def]
    return await k.coordinator.start_run(k.requester, "write standup note", k.scope)


def test_the_fallback_codes_are_exactly_the_mapped_ones() -> None:
    assert set(FALLBACK_MESSAGES) == set(FALLBACK_CODES)
    assert set(FALLBACK_FEATURES) == set(FALLBACK_CODES)
    assert set(FALLBACK_FEATURES.values()) == set(Features.model_fields)
    assert all(m.strip() for m in FALLBACK_MESSAGES.values())


def test_phase3_codes_have_fixed_messages() -> None:
    """The eight Phase 3 codes of ADR 0032 §11 (``GROUNDED`` lands with Task 3e.2): three
    fallback codes, five terminal ones, each with one fixed message and a ``classify``
    group; a terminal code is never a fallback code."""
    phase3_fallback = {c for c in FALLBACK_CODES if FALLBACK_FEATURES[c] != "execution_ir"}
    codes = phase3_fallback | set(PHASE3_TERMINAL)
    assert len(codes) == 8
    assert set(TERMINAL_MESSAGES) == set(PHASE3_TERMINAL)
    assert not set(TERMINAL_MESSAGES) & set(FALLBACK_MESSAGES)
    messages = [FALLBACK_MESSAGES[c] for c in phase3_fallback]
    messages += [TERMINAL_MESSAGES[c] for c in PHASE3_TERMINAL]
    assert all(m.strip() and m.endswith(".") for m in messages)
    assert len(set(messages)) == len(messages), "each code has its own message"
    for code, group in PHASE3_TERMINAL.items():
        label = classify("FAILED", "x", "fixture", code)
        if group is BLOCKED_BY_DESIGN:
            assert code in BLOCKED_BY_DESIGN and label == "fixture:blocked-by-design", code
        elif group is INFRASTRUCTURE_OR_BUDGET:
            assert code in INFRASTRUCTURE_OR_BUDGET, code
            assert label == "fixture:infrastructure-or-budget", code
        else:
            assert label == "fixture:failed", code
    for code in phase3_fallback:  # never ends a run, so in no terminal group
        assert code not in BLOCKED_BY_DESIGN | INFRASTRUCTURE_OR_BUDGET, code
    print(f"phase 3 codes: {len(codes)}")


def _code_arg(call: ast.Call, index: int | None) -> ast.expr | None:
    """The ``code`` argument of ``call``: by keyword, or at positional ``index`` (no self)."""
    for kw in call.keywords:
        if kw.arg == "code":
            return kw.value
    if index is not None and len(call.args) > index:
        return call.args[index]
    return None


def _set_run_state_codes() -> list[str]:
    """Every reason code a kernel state change can carry: the ``ReasonCode.X`` passed to
    ``_set_run_state``, or to a helper that forwards its own ``code`` parameter to it (whose
    callers and default are read instead). Any other form cannot be checked here, so it is
    returned as ``<unresolvable ...>`` and refused."""
    trees = [
        (path.name, ast.parse(path.read_text("utf-8"))) for path in sorted(KERNEL.glob("*.py"))
    ]
    forwarders: dict[str, tuple[int | None, ast.expr | None]] = {"_set_run_state": (None, None)}
    for _, tree in trees:  # helpers whose `code` parameter reaches `_set_run_state`
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            params = [a.arg for a in fn.args.args[1:]]  # without self
            if "code" not in params:
                continue
            index = params.index("code")
            defaults = dict(zip(reversed(params), reversed(fn.args.defaults), strict=False))
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "_set_run_state"
                    and isinstance(_code_arg(node, None), ast.Name)
                ):
                    forwarders[fn.name] = (index, defaults.get("code"))
    codes: list[str] = []
    for _, default in forwarders.values():
        if isinstance(default, ast.Attribute):
            codes.append(default.attr)
    for filename, tree in trees:
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in forwarders
            ):
                continue
            index, _ = forwarders[node.func.attr]
            value = _code_arg(node, index)
            if value is None or (isinstance(value, ast.Constant) and value.value is None):
                continue
            if isinstance(value, ast.Attribute):
                codes.append(value.attr)
            elif not (isinstance(value, ast.Name) and value.id == "code"):  # a forwarder's own
                codes.append(f"<unresolvable at {filename}:{node.lineno}>")
    return codes


@pytest.mark.parametrize("reason", FALLBACK_CODES)
async def test_fallback_codes_never_end_a_run(make_kernel: MakeKernel, reason: ReasonCode) -> None:
    """ADR 0027: a fallback code is carried only by ``feature.fallback``. Recording one leaves
    the run's state and code as they were, and no kernel state change names one."""
    k = make_kernel()
    run = await _start(k)
    updated = await k.coordinator.record_fallback(run, FALLBACK_FEATURES[reason], reason)
    stored = await k.store.get_run(TENANT, run.run_id)
    assert (updated.state, stored.state) == (run.state, run.state)
    assert stored.reason_code == run.reason_code != reason
    codes = _set_run_state_codes()
    assert codes, "no _set_run_state call was scanned"
    assert not [c for c in codes if c.startswith("<")], "pass the code as ReasonCode.X"
    assert reason.name not in codes, f"{reason} ends a run in the kernel"
    print(f"state changes scanned: {len(codes)}")


async def test_record_fallback_appends_event_with_reason(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    before = await k.store.list_events(TENANT, run.run_id)

    updated = await k.coordinator.record_fallback(run, "execution_ir", ReasonCode.IR_COMPILE_FAILED)

    events = await k.store.list_events(TENANT, run.run_id)
    assert len(events) == len(before) + 1
    event = events[-1]
    assert event.type is RunEventType.FEATURE_FALLBACK
    assert event.payload == {
        "feature": "execution_ir",
        "reason_code": "ir_compile_failed",
        "message": FALLBACK_MESSAGES[ReasonCode.IR_COMPILE_FAILED],
    }
    assert event.action_id is None
    stored = await k.store.get_run(TENANT, run.run_id)
    assert updated.revision == stored.revision == run.revision + 1
    assert stored.state is run.state, "a fallback never changes the run state"
    assert stored.reason_code == run.reason_code


@pytest.mark.parametrize("reason", FALLBACK_CODES)
async def test_record_fallback_payload_is_fixed_per_reason(
    make_kernel: MakeKernel, reason: ReasonCode
) -> None:
    k = make_kernel()
    run = await _start(k)
    feature = FALLBACK_FEATURES[reason]
    await k.coordinator.record_fallback(run, feature, reason)
    event = (await k.store.list_events(TENANT, run.run_id))[-1]
    assert event.payload == {
        "feature": feature,
        "reason_code": reason.value,
        "message": FALLBACK_MESSAGES[reason],
    }


async def test_record_fallback_refuses_another_features_code(make_kernel: MakeKernel) -> None:
    """A fallback code belongs to the feature its ADR names it for."""
    k = make_kernel()
    run = await _start(k)
    with pytest.raises(KernelError) as exc:
        await k.coordinator.record_fallback(run, "execution_ir", ReasonCode.CONTEXT_ASSEMBLY_FAILED)
    assert exc.value.code is ErrorCode.INVALID_REQUEST
    types = [e.type for e in await k.store.list_events(TENANT, run.run_id)]
    assert RunEventType.FEATURE_FALLBACK not in types


@pytest.mark.parametrize("reason", NOT_FALLBACK_CODES)
async def test_record_fallback_refuses_non_fallback_reason(
    make_kernel: MakeKernel, reason: ReasonCode
) -> None:
    k = make_kernel()
    run = await _start(k)
    with pytest.raises(KernelError) as exc:
        await k.coordinator.record_fallback(run, "execution_ir", reason)
    assert exc.value.code is ErrorCode.INVALID_REQUEST
    types = [e.type for e in await k.store.list_events(TENANT, run.run_id)]
    assert RunEventType.FEATURE_FALLBACK not in types


async def test_record_fallback_refuses_unknown_feature(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    with pytest.raises(KernelError) as exc:
        await k.coordinator.record_fallback(run, "no_such_feature", ReasonCode.IR_COMPILE_FAILED)
    assert exc.value.code is ErrorCode.INVALID_REQUEST
    types = [e.type for e in await k.store.list_events(TENANT, run.run_id)]
    assert RunEventType.FEATURE_FALLBACK not in types


async def test_record_fallback_refuses_a_terminal_run(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    run = await k.coordinator.decide(
        actor=k.approver,
        run_id=run.run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.REJECTED,
    )
    assert run.state is RunState.FAILED
    with pytest.raises(KernelError) as exc:
        await k.coordinator.record_fallback(run, "execution_ir", ReasonCode.IR_COMPILE_FAILED)
    assert exc.value.code is ErrorCode.CONFLICT


async def test_fallback_event_and_evidence_carry_no_caller_text(make_kernel: MakeKernel) -> None:
    # The API has no parameter for caller text, positional or keyword.
    params = inspect.signature(type(make_kernel().coordinator).record_fallback).parameters
    assert list(params) == ["self", "run", "feature", "reason"]
    assert all(
        p.kind is not p.VAR_POSITIONAL and p.kind is not p.VAR_KEYWORD for p in params.values()
    )

    k = make_kernel()
    run = await _start(k)
    secret = "sk-synthetic-0123456789"
    with pytest.raises(TypeError):
        await k.coordinator.record_fallback(  # type: ignore[call-arg]
            run, "execution_ir", ReasonCode.IR_VALIDATION_FAILED, secret
        )
    with pytest.raises(TypeError):
        await k.coordinator.record_fallback(  # type: ignore[call-arg]
            run, "execution_ir", ReasonCode.IR_VALIDATION_FAILED, detail=secret
        )
    await k.coordinator.record_fallback(run, "execution_ir", ReasonCode.IR_VALIDATION_FAILED)

    bundle = await build_evidence(
        k.store, TENANT, run.run_id, environment="fixture", versions={}, features=Features()
    )
    exported = [e for e in bundle["events"] if e["type"] == "feature.fallback"]
    assert [e["payload"] for e in exported] == [
        {
            "feature": "execution_ir",
            "reason_code": "ir_validation_failed",
            "message": FALLBACK_MESSAGES[ReasonCode.IR_VALIDATION_FAILED],
        }
    ]
    assert secret not in json.dumps(bundle)
