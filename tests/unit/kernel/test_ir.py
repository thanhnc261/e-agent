"""The kernel's pure IR functions (ADR 0025, target §6.4.3-§6.4.5): compile, validate, digest.

Task definitions, descriptors and contexts are built inline: no plugin is imported here
(`tests/conformance/test_kernel_tests_neutral.py`).
"""

from __future__ import annotations

import ast
import copy
import inspect
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from typing import Any
from unittest import mock

import e_agent.kernel.ir as ir
import pytest
from e_agent.contracts.capability import EffectKind
from e_agent.contracts.digest import CanonicalizationError
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.plan import (
    ActionPlan,
    ActionProposal,
    LineageRef,
    PlannedStep,
    plan_from_wire,
)
from e_agent.contracts.task import AcceptanceSpec, TaskDefinition
from e_agent.contracts.validation import ValidationStatus
from e_agent.kernel.approval import compute_digest, digest_input, fact_digest
from e_agent.kernel.ir import (
    PlanValidationContext,
    StepDigestContext,
    compile_proposal,
    plan_digest,
    plan_digest_input,
    step_operation_id,
    validate_plan,
)
from pydantic_core import SchemaSerializer

WRITE_A = "notes.note.create.v1"
WRITE_B = "notes.tag.attach.v1"
ANSWER = "notes.summary.answer.v1"
READ = "notes.note.read.v1"
OUTSIDE = "notes.note.delete.v1"
EFFECTS = {
    WRITE_A: EffectKind.WRITE,
    WRITE_B: EffectKind.WRITE,
    ANSWER: EffectKind.ANSWER,
    READ: EffectKind.READ,
    OUTSIDE: EffectKind.WRITE,
}
AT = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


def _task(*capabilities: str) -> TaskDefinition:
    return TaskDefinition(
        task_id="notes.capture",
        version="1",
        title="Capture a note",
        goal_template="Capture {note}",
        capabilities=capabilities or (WRITE_A, WRITE_B, ANSWER, READ),
        acceptance=AcceptanceSpec(),
    )


def _proposal(contract_id: str = WRITE_A, **arguments: Any) -> ActionProposal:
    return ActionProposal(
        contract_id=contract_id,
        connection_id="conn_notes",
        arguments=arguments or {"title": "t"},
        expected_effects=("note.created",),
    )


def _step(step_id: str, contract_id: str = WRITE_A, *deps: str, **args: Any) -> PlannedStep:
    return PlannedStep(step_id=step_id, proposal=_proposal(contract_id, **args), depends_on=deps)


def _plan(*steps: PlannedStep, plan_id: str = "plan_1") -> ActionPlan:
    return ActionPlan(plan_id=plan_id, task_id="notes.capture", task_version="1", steps=steps)


def _ctx(
    max_writes: int = 1, effects: dict[str, EffectKind] | None = None
) -> PlanValidationContext:
    return PlanValidationContext(
        effects=EFFECTS if effects is None else effects, max_admitted_writes=max_writes
    )


def _evidence(evidence_id: str, revision: str | None) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        tenant_id="t1",
        source="notes",
        locator=f"note/{evidence_id}",
        revision=revision,
        observed_at=AT,
        scope="tenant:t1",
    )


def _step_context(**overrides: Any) -> StepDigestContext:
    fields: dict[str, Any] = {
        "tenant_id": "t1",
        "requester_id": "u1",
        "binding_id": "notes.local.create",
        "connection_version": 3,
        "credential_subject": "svc-notes",
        "credential_version": "cred-v2",
        "evidence": (),
        "fact_digests": {},
        "rule_bundle_version": "notes-rules-v1",
        "policy_version": "policy-v1",
    }
    return StepDigestContext(**{**fields, **overrides})


# -- compile -----------------------------------------------------------------------------
def test_single_proposal_compiles_to_one_step_plan() -> None:
    proposal = _proposal(title="Ghi chú", tags=["a", "b"])
    plan = compile_proposal(proposal, _task(), plan_id="plan_run1")
    assert plan.plan_id == "plan_run1"
    assert (plan.task_id, plan.task_version) == ("notes.capture", "1")
    assert len(plan.steps) == 1
    (step,) = plan.steps
    assert step.step_id == ir.SINGLE_STEP_ID
    assert step.depends_on == ()
    assert step.proposal == proposal
    # Deterministic: the same inputs compile to an equal plan.
    assert compile_proposal(proposal, _task(), plan_id="plan_run1") == plan


# -- digest ------------------------------------------------------------------------------
def _today_action_digest_input(proposal: ActionProposal, ctx: StepDigestContext) -> dict[str, Any]:
    """Build the digest input the way `kernel/proposals.py` `_handle_proposal` does today."""
    observations = {
        "ev_fact": {"note": "Đơn mua hàng nháp", "lines": ["1", "2"]},
        "ev_rev": {"note": "revisioned"},
    }
    evidence = [_evidence("ev_fact", None), _evidence("ev_rev", "r7")]
    return digest_input(
        tenant_id=ctx.tenant_id,
        requester_id=ctx.requester_id,
        logical_operation_id="op_run",
        contract_id=proposal.contract_id,
        binding_id=ctx.binding_id,
        connection_id=proposal.connection_id,
        connection_version=ctx.connection_version,
        credential_subject=ctx.credential_subject,
        arguments=dict(proposal.arguments),
        expected_effects=proposal.expected_effects,
        evidence=evidence,
        rule_bundle_version=ctx.rule_bundle_version,
        policy_version=ctx.policy_version,
        credential_version=ctx.credential_version,
        fact_digests={
            e.evidence_id: fact_digest(observations[e.evidence_id])
            for e in evidence
            if e.revision is None
        },
    )


def _one_step_fixture() -> tuple[ActionPlan, dict[str, StepDigestContext], dict[str, Any]]:
    proposal = _proposal(
        title="Đơn mua hàng nháp", lines=[{"sku": "A-1", "qty": "4"}], meta={"tag": None}
    )
    evidence = (_evidence("ev_fact", None), _evidence("ev_rev", "r7"))
    ctx = _step_context(
        evidence=evidence,
        fact_digests={"ev_fact": fact_digest({"note": "Đơn mua hàng nháp", "lines": ["1", "2"]})},
    )
    plan = compile_proposal(proposal, _task(), plan_id="plan_run1")
    return plan, {ir.SINGLE_STEP_ID: ctx}, _today_action_digest_input(proposal, ctx)


def test_one_step_plan_digest_equals_action_digest() -> None:
    plan, contexts, today = _one_step_fixture()
    built = plan_digest_input(plan, contexts, run_operation_id="op_run")
    assert built == today
    assert "plan_schema" not in built
    assert plan_digest(plan, contexts, run_operation_id="op_run") == compute_digest(today)
    # The evidence without a revision binds its fact digest; the revisioned one does not.
    by_id = {e["id"]: e for e in built["evidence"]}
    assert by_id["ev_fact"]["fact_digest"].startswith("facts-json-v1:")
    assert by_id["ev_rev"]["fact_digest"] == ""


@contextmanager
def _lineage_serializer_spy() -> Iterator[list[object]]:
    """Count calls of the `LineageRef` wire serializer, also when it is nested in `Any`."""
    schema = copy.deepcopy(LineageRef.__pydantic_core_schema__)
    inner: Any = schema["schema"]  # type: ignore[typeddict-item]
    original = inner["serialization"]["function"]
    calls: list[object] = []

    def counting(value: object) -> object:
        calls.append(value)
        return original(value)

    inner["serialization"]["function"] = counting
    with mock.patch.object(LineageRef, "__pydantic_serializer__", SchemaSerializer(schema)):
        yield calls


def test_one_step_plan_digest_skips_the_lineage_serializer() -> None:
    plan, contexts, today = _one_step_fixture()
    two_step = _plan(_step("a"), _step("b", WRITE_B, "a", note=LineageRef(step_id="a", path="/id")))
    two_contexts = {"a": _step_context(), "b": _step_context()}
    with _lineage_serializer_spy() as calls:
        # Positive control: a placeholder goes through the spied serializer.
        plan_digest_input(two_step, two_contexts, run_operation_id="op_run")
        assert len(calls) == 1
        calls.clear()
        with mock.patch.object(ir, "plan_to_wire", side_effect=AssertionError("wire form")):
            assert plan_digest_input(plan, contexts, run_operation_id="op_run") == today
        assert calls == []


def _two_step_with(**arguments: Any) -> tuple[ActionPlan, dict[str, StepDigestContext]]:
    plan = _plan(
        _step("a"),
        _step("b", WRITE_B, "a", note=LineageRef(step_id="a", path="/id"), **arguments),
    )
    return plan, {"a": _step_context(), "b": _step_context()}


# Values the 1-step path refuses at canonicalization; a JSON-mode dump would coerce each one
# (a set to a hash-ordered list, Decimal/NaN/inf to strings or null, an int key to a string,
# bytes to str), so the 2+-step path must refuse them too (2c.4 review R-1).
NON_PROFILE = {
    "multi-element set": {"x", "y", "z"},
    "set holding a placeholder": {LineageRef(step_id="a", path="/id")},
    "decimal": Decimal("4"),
    "nan": float("nan"),
    "inf": float("inf"),
    "int key": {1: "a"},
    "bytes": b"4",
}


@pytest.mark.parametrize("value", list(NON_PROFILE.values()), ids=list(NON_PROFILE))
def test_multi_step_digest_refuses_what_the_one_step_path_refuses(value: object) -> None:
    with pytest.raises(CanonicalizationError):
        compute_digest({"arguments": {"v": value}})  # today's 1-step behaviour
    plan, contexts = _two_step_with(v=value)
    with pytest.raises(CanonicalizationError):
        plan_digest(plan, contexts, run_operation_id="op_run")


def test_multi_step_digest_input_keeps_python_values_and_encodes_placeholders() -> None:
    """Only each `LineageRef` is replaced; every other value passes through unchanged."""
    ref = LineageRef(step_id="a", path="/id")
    plan, contexts = _two_step_with(
        nested={"list": ["x", ref], "tuple": ("t", ref)}, flag=True, empty=None
    )
    arguments = plan_digest_input(plan, contexts, run_operation_id="op_run")["steps"][1]["input"][
        "arguments"
    ]
    wire = {"$lineage": {"step": "a", "path": "/id"}}
    assert arguments == {
        "note": wire,
        "nested": {"list": ["x", wire], "tuple": ["t", wire]},
        "flag": True,
        "empty": None,
    }
    assert arguments["flag"] is True and arguments["empty"] is None


def test_multi_step_digest_refuses_a_forged_literal_placeholder() -> None:
    plan, contexts = _two_step_with()
    plan.steps[1].proposal.arguments["forged"] = {"$lineage": {"step": "a", "path": "/x"}}
    with pytest.raises(ValueError, match=r"\$lineage"):
        plan_digest_input(plan, contexts, run_operation_id="op_run")


def test_multi_step_digest_is_stable_across_hash_seeds() -> None:
    """A set argument is refused in every process; a JSON-mode dump would list it in hash
    order, so its digest would differ with `PYTHONHASHSEED`."""
    script = (
        "import json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from test_ir import _two_step_with\n"
        "from e_agent.contracts.digest import CanonicalizationError\n"
        "from e_agent.kernel.ir import plan_digest\n"
        "plan, contexts = _two_step_with(tags={'x', 'y', 'z', 'w', 'v'})\n"
        "try:\n"
        "    print(plan_digest(plan, contexts, run_operation_id='op_run'))\n"
        "except CanonicalizationError:\n"
        "    print('refused')\n"
    )
    here = str(Path(__file__).parent)
    digests = {
        subprocess.run(
            [sys.executable, "-c", script, here],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for seed in ("1", "2", "3", "4")
    }
    assert digests == {"refused"}


def test_multi_step_digest_input_wraps_steps_in_index_order() -> None:
    plan = _plan(
        _step("a"),
        _step("b", WRITE_B),
        _step("c", WRITE_A, "b", "a", note=LineageRef(step_id="b", path="/name")),
    )
    contexts = {s.step_id: _step_context() for s in plan.steps}
    built = plan_digest_input(plan, contexts, run_operation_id="op_run")
    assert built["plan_schema"] == "plan.v1"
    assert [s["step_id"] for s in built["steps"]] == ["a", "b", "c"]
    assert built["steps"][2]["depends_on"] == ["a", "b"]
    inputs = [s["input"] for s in built["steps"]]
    assert [i["logical_operation_id"] for i in inputs] == [
        step_operation_id("plan_1", "a"),
        step_operation_id("plan_1", "b"),
        step_operation_id("plan_1", "c"),
    ]
    assert inputs[2]["arguments"] == {"note": {"$lineage": {"step": "b", "path": "/name"}}}


def test_step_operation_id_is_derived_from_plan_and_step() -> None:
    first = step_operation_id("plan_1", "a")
    assert first == step_operation_id("plan_1", "a")
    assert first.startswith("op_") and len(first) == len("op_") + 32
    assert first != step_operation_id("plan_1", "b")
    assert first != step_operation_id("plan_2", "a")
    # No separator ambiguity between the two parts.
    assert step_operation_id("p:a", "b") != step_operation_id("p", "a:b")


def test_plan_digest_input_needs_every_step_context() -> None:
    plan = _plan(_step("a"), _step("b", WRITE_B, "a"))
    with pytest.raises(ValueError, match="'b'"):
        plan_digest_input(plan, {"a": _step_context()}, run_operation_id="op_run")


def test_plan_digest_changes_when_dependency_or_path_changes() -> None:
    def digest_of(path: str, deps: tuple[str, ...]) -> str:
        plan = _plan(
            _step("a"),
            _step("b", WRITE_B),
            _step("c", WRITE_A, *deps, note=LineageRef(step_id="a", path=path)),
        )
        contexts = {s.step_id: _step_context() for s in plan.steps}
        return plan_digest(plan, contexts, run_operation_id="op_run")

    base = digest_of("/id", ("a",))
    assert digest_of("/id", ("a",)) == base
    assert digest_of("/name", ("a",)) != base
    assert digest_of("/id", ("a", "b")) != base


# -- golden vectors -----------------------------------------------------------------------
def _vectors() -> list[dict[str, Any]]:
    raw = files("e_agent.contracts").joinpath("golden/digest_vectors.json").read_text("utf-8")
    return json.loads(raw)["vectors"]  # type: ignore[no-any-return]


def _rebuild(vector: dict[str, Any]) -> tuple[ActionPlan, dict[str, StepDigestContext]]:
    plan = plan_from_wire(vector["plan"])
    contexts = {
        step_id: StepDigestContext.model_validate(body)
        for step_id, body in vector["step_contexts"].items()
    }
    return plan, contexts


def test_plan_digest_golden_vectors() -> None:
    vectors = [v for v in _vectors() if v.get("kind") == "plan"]
    print(f"plan digest golden vectors: {len(vectors)}")
    assert len(vectors) >= 3
    sizes = set()
    for vector in vectors:
        plan, contexts = _rebuild(vector)
        sizes.add(len(plan.steps))
        built = plan_digest_input(plan, contexts, run_operation_id=vector["run_operation_id"])
        assert built == vector["input"], vector["name"]
        digest = plan_digest(plan, contexts, run_operation_id=vector["run_operation_id"])
        assert digest == vector["digest"], vector["name"]
        if len(plan.steps) > 1:
            assert any("$lineage" in json.dumps(s["input"]["arguments"]) for s in built["steps"])
    assert {1, 2, 3} <= sizes


def test_one_step_golden_vector_equals_the_action_vector() -> None:
    by_name = {v["name"]: v for v in _vectors()}
    one = by_name["1-step plan (a compiled proposal)"]
    action = by_name["action digest input (today's proposal path)"]
    assert one["input"] == action["input"]
    assert one["digest"] == action["digest"] == compute_digest(action["input"])
    # The action vector is today's `digest_input`, built without the IR functions.
    plan, contexts = _rebuild(one)
    (step,) = plan.steps
    ctx, proposal = contexts[step.step_id], step.proposal
    today = digest_input(
        tenant_id=ctx.tenant_id,
        requester_id=ctx.requester_id,
        logical_operation_id=one["run_operation_id"],
        contract_id=proposal.contract_id,
        binding_id=ctx.binding_id,
        connection_id=proposal.connection_id,
        connection_version=ctx.connection_version,
        credential_subject=ctx.credential_subject,
        arguments=dict(proposal.arguments),
        expected_effects=proposal.expected_effects,
        evidence=ctx.evidence,
        rule_bundle_version=ctx.rule_bundle_version,
        policy_version=ctx.policy_version,
        credential_version=ctx.credential_version,
        fact_digests=ctx.fact_digests,
    )
    assert today == action["input"]


# -- validate ----------------------------------------------------------------------------
def _codes(findings: tuple[Any, ...]) -> list[str]:
    return [f.rule_id for f in findings]


def test_validate_accepts_a_plan_inside_its_definition() -> None:
    plan = compile_proposal(_proposal(), _task(), plan_id="plan_run1")
    assert validate_plan(plan, _task(), _ctx()) == ()
    two = _plan(_step("a"), _step("b", WRITE_B, "a", note=LineageRef(step_id="a", path="/id")))
    assert validate_plan(two, _task(), _ctx(max_writes=2)) == ()


def test_validate_rejects_capability_outside_task_definition() -> None:
    plan = _plan(_step("a"), _step("b", OUTSIDE, "a"))
    findings = validate_plan(plan, _task(), _ctx(max_writes=5))
    assert _codes(findings) == ["KERNEL-PLAN-CAPABILITY"]
    assert findings[0].status is ValidationStatus.FAIL
    assert OUTSIDE in findings[0].message


def test_validate_rejects_write_count_over_budget() -> None:
    plan = _plan(_step("a"), _step("b", WRITE_B, "a"), _step("c", ANSWER, "b"))
    assert _codes(validate_plan(plan, _task(), _ctx(max_writes=1))) == ["KERNEL-PLAN-WRITES"]
    # Only writes count: an answer step uses no write budget.
    assert validate_plan(plan, _task(), _ctx(max_writes=2)) == ()


def test_validate_rejects_capability_without_resolved_effect() -> None:
    plan = _plan(_step("a"))
    effects = {k: v for k, v in EFFECTS.items() if k != WRITE_A}
    assert _codes(validate_plan(plan, _task(), _ctx(effects=effects))) == [
        "KERNEL-PLAN-UNKNOWN-CAPABILITY"
    ]


def test_validate_rejects_a_read_step() -> None:
    plan = _plan(_step("a", READ))
    assert _codes(validate_plan(plan, _task(), _ctx())) == ["KERNEL-PLAN-READ-STEP"]


def test_validate_rejects_plan_for_another_definition() -> None:
    plan = ActionPlan(plan_id="p", task_id="notes.capture", task_version="2", steps=(_step("a"),))
    assert _codes(validate_plan(plan, _task(), _ctx())) == ["KERNEL-PLAN-TASK"]


def test_validate_revalidates_a_built_plan_without_raising() -> None:
    """A literal `$lineage` set on a built plan's mutable arguments is a finding, not a raise
    and not a placeholder: the plan rules are re-applied through the wire form."""
    plan = _plan(_step("a"), _step("b", WRITE_B, "a", note=LineageRef(step_id="a", path="/id")))
    plan.steps[1].proposal.arguments["forged"] = {"$lineage": {"step": "a", "path": "/x"}}
    assert _codes(validate_plan(plan, _task(), _ctx(max_writes=2))) == ["KERNEL-PLAN-STRUCTURE"]
    unchecked = ActionPlan.model_construct(
        plan_id="p", task_id="notes.capture", task_version="1", steps=()
    )
    assert _codes(validate_plan(unchecked, _task(), _ctx())) == ["KERNEL-PLAN-STRUCTURE"]


def test_validate_reports_arguments_outside_the_digest_profile() -> None:
    one = compile_proposal(_proposal(qty=Decimal("4")), _task(), plan_id="plan_run1")
    findings = validate_plan(one, _task(), _ctx())
    assert _codes(findings) == ["KERNEL-ARGS"]
    assert "arguments outside the digest profile" in findings[0].message
    plan, _ = _two_step_with(tags={"x", "y"})
    findings = validate_plan(plan, _task(), _ctx(max_writes=2))
    assert _codes(findings) == ["KERNEL-ARGS"]
    assert "'b'" in findings[0].message
    # Placeholders count as their wire form, which is inside the profile.
    plan, _ = _two_step_with()
    assert validate_plan(plan, _task(), _ctx(max_writes=2)) == ()


IR_SOURCE = Path(inspect.getfile(ir))
ALLOWED_IMPORTS = (
    "__future__",
    "collections.abc",
    "hashlib",
    "typing",
    "pydantic",
    "e_agent.contracts.",
    "e_agent.kernel.approval",
)


def _imports(source: str) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import in kernel/ir.py"
            names.append(node.module or "")
    return names


def test_validate_is_pure() -> None:
    source = IR_SOURCE.read_text("utf-8")
    imports = _imports(source)
    assert imports, "no imports parsed"
    outside = [m for m in imports if not m.startswith(ALLOWED_IMPORTS) and m not in ALLOWED_IMPORTS]
    assert outside == [], f"kernel/ir.py imports beyond contracts and approval: {outside}"
    for banned in ("e_agent.sdk", "e_agent.kernel.memory_store", "e_agent.kernel.registry"):
        assert not any(m.startswith(banned) for m in imports)
    tree = ast.parse(source)
    assert not any(isinstance(n, ast.AsyncFunctionDef | ast.Await) for n in ast.walk(tree))
    assert not inspect.iscoroutinefunction(validate_plan)
    # The context is plain data: no store, driver, registry or client field.
    assert set(PlanValidationContext.model_fields) == {"effects", "max_admitted_writes"}
    plan = _plan(_step("a"), _step("b", OUTSIDE, "a"))
    before = plan.model_dump(mode="json")
    first = validate_plan(plan, _task(), _ctx())
    assert validate_plan(plan, _task(), _ctx()) == first
    assert plan.model_dump(mode="json") == before
