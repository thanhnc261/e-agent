from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.capability import CapabilityBinding, CapabilityDescriptor, EffectKind
from e_agent.contracts.common import Record
from e_agent.contracts.plan import ActionPlan, ActionProposal, LineageRef, PlannedStep
from e_agent.contracts.run import RunRecord, RunState
from e_agent.contracts.step import StepKind, StepRecord, StepStatus, StepUsage
from e_agent.contracts.task import AcceptanceSpec, RequiredEffect, TaskDefinition
from pydantic import ValidationError


def _proposal(contract_id: str = "erp.purchase.create.v1", **arguments: Any) -> ActionProposal:
    return ActionProposal(contract_id=contract_id, connection_id="c1", arguments=arguments)


def _step(step_id: str, *depends_on: str, **arguments: Any) -> PlannedStep:
    return PlannedStep(step_id=step_id, proposal=_proposal(**arguments), depends_on=depends_on)


def _plan(*steps: PlannedStep) -> ActionPlan:
    return ActionPlan(plan_id="plan_1", task_id="purchase_order", task_version="1", steps=steps)


def test_action_plan_accepts_ordered_steps_with_lineage() -> None:
    ref = LineageRef(step_id="s1", path="/partner_id")
    plan = _plan(_step("s1", qty="1"), _step("s2", "s1", vendor=ref, lines=[{"ref": ref}]))
    assert [s.step_id for s in plan.steps] == ["s1", "s2"]
    assert plan.steps[1].proposal.arguments["vendor"] is ref


def test_action_plan_requires_a_step() -> None:
    with pytest.raises(ValidationError, match="at least one step"):
        _plan()


def test_action_plan_rejects_duplicate_step_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate step id 's1'"):
        _plan(_step("s1"), _step("s1"))


def test_action_plan_rejects_unknown_dependency() -> None:
    with pytest.raises(ValidationError, match="unknown step 'missing'"):
        _plan(_step("s1"), _step("s2", "missing"))


def test_action_plan_rejects_cycle() -> None:
    with pytest.raises(ValidationError, match="dependency cycle"):
        _plan(_step("s1", "s2"), _step("s2", "s1"))
    with pytest.raises(ValidationError, match="depends on itself"):
        _step("s1", "s1")


def test_action_plan_rejects_dependency_on_a_later_step() -> None:
    with pytest.raises(ValidationError, match="later step 's2'"):
        _plan(_step("s1", "s2"), _step("s2"))


def test_lineage_ref_must_point_to_an_earlier_dependency() -> None:
    ref = LineageRef(step_id="s1", path="/partner_id")
    with pytest.raises(ValidationError, match="not in depends_on"):
        _step("s2", vendor=ref)
    nested = LineageRef(step_id="s0", path="/id")
    with pytest.raises(ValidationError, match="not in depends_on"):
        _step("s2", "s1", lines=[{"product": nested}])
    # A placeholder naming a dependency that is not earlier fails on the plan's order rule.
    with pytest.raises(ValidationError, match="later step 's2'"):
        _plan(_step("s1", "s2", vendor=LineageRef(step_id="s2", path="/id")), _step("s2"))


def test_lineage_key_literal_refused() -> None:
    literal = {"$lineage": {"step": "s1", "path": "/partner_id"}}
    with pytest.raises(ValidationError, match=r"\$lineage"):
        _step("s2", "s1", vendor=literal)
    with pytest.raises(ValidationError, match=r"\$lineage"):
        _step("s2", "s1", lines=[{"ok": 1}, {"nested": literal}])
    with pytest.raises(ValidationError, match=r"\$lineage"):
        _step("s2", "s1", **{"$lineage": "x"})


def test_lineage_ref_has_step_and_path_only() -> None:
    assert list(LineageRef.model_fields) == ["step_id", "path"]
    assert "lineage" not in PlannedStep.model_fields
    assert LineageRef(step_id="s1", path="").path == ""
    with pytest.raises(ValidationError):
        LineageRef(step_id="s1", path="/x", rule="copy")  # type: ignore[call-arg]
    with pytest.raises(ValidationError, match="JSON pointer"):
        LineageRef(step_id="s1", path="partner_id")
    with pytest.raises(ValidationError, match="JSON pointer"):
        LineageRef(step_id="s1", path="/a~2b")


def test_lineage_ref_path_is_a_strict_json_pointer() -> None:
    for valid in ("", "/", "/a", "/a/0", "/a~0b", "/a~1b", "/~0~1", "/line\nbreak", "/ space"):
        assert LineageRef(step_id="s1", path=valid).path == valid
    for invalid in ("\n", "/a\n~", "a", "/a~", "/a~2"):
        with pytest.raises(ValidationError, match="JSON pointer"):
            LineageRef(step_id="s1", path=invalid)
    with pytest.raises(ValidationError, match="JSON pointer"):
        LineageRef.model_validate_json('{"step_id": "s1", "path": "\\n"}')
    with pytest.raises(ValidationError, match="JSON pointer"):
        LineageRef.model_validate_json('{"step_id": "s1", "path": "/a\\n~"}')


def test_lineage_ref_path_rejects_trailing_newline() -> None:
    # `re.match` with `$` would accept these: `$` matches before a final newline.
    for invalid in ("\n", "/a~2\n", "/a~\n"):
        with pytest.raises(ValidationError, match="JSON pointer"):
            LineageRef(step_id="s1", path=invalid)


def test_constructed_lineage_ref_with_bad_path_rejected() -> None:
    for bad in ("\n", "/bad~2", "relative"):
        ref = LineageRef.model_construct(step_id="s1", path=bad)
        with pytest.raises(ValidationError, match="JSON pointer"):
            LineageRef.model_validate(ref)
    not_text = LineageRef.model_construct(step_id="s1", path=7)
    with pytest.raises(ValidationError, match="JSON pointer"):
        LineageRef.model_validate(not_text)
    good = LineageRef.model_construct(step_id="s1", path="/a~0b/~1c")
    assert LineageRef.model_validate(good) is good


def _nested(ref: LineageRef) -> tuple[dict[str, list[LineageRef]], ...]:
    return ({"lines": [ref]},)


def test_plan_with_constructed_bad_lineage_ref_rejected() -> None:
    for bad in ("\n", "/bad~2"):
        plan = _plan(
            _step("s1"), _step("s2", "s1", deep=_nested(LineageRef(step_id="s1", path="/id")))
        )
        plan.steps[1].proposal.arguments["deep"] = _nested(
            LineageRef.model_construct(step_id="s1", path=bad)
        )
        with pytest.raises(ValidationError, match="JSON pointer"):
            ActionPlan.model_validate(plan)
        # A fresh step refuses it too: the walker checks every ref it meets.
        with pytest.raises(ValidationError, match="JSON pointer"):
            _step("s2", "s1", deep=_nested(LineageRef.model_construct(step_id="s1", path=bad)))


def test_model_construct_plan_with_bad_lineage_ref_rejected() -> None:
    for bad in ("\n", "/bad~2"):
        ref = LineageRef.model_construct(step_id="s1", path=bad)
        steps = (
            PlannedStep.model_construct(step_id="s1", proposal=_proposal(), depends_on=()),
            PlannedStep.model_construct(
                step_id="s2", proposal=_proposal(deep=_nested(ref)), depends_on=("s1",)
            ),
        )
        plan = ActionPlan.model_construct(
            plan_id="plan_1", task_id="purchase_order", task_version="1", steps=steps
        )
        with pytest.raises(ValidationError, match="JSON pointer"):
            ActionPlan.model_validate(plan)


def test_revalidating_mutated_plan_rejects_lineage_literal() -> None:
    plan = _plan(_step("s1"), _step("s2", "s1", lines=[{"ok": 1}]))
    plan.steps[1].proposal.arguments["lines"][0]["vendor"] = {
        "$lineage": {"step": "s1", "path": "/partner_id"}
    }
    with pytest.raises(ValidationError, match=r"\$lineage"):
        ActionPlan.model_validate(plan)
    with pytest.raises(ValidationError, match=r"\$lineage"):
        ActionPlan.model_validate(plan.model_dump())


def test_revalidating_mutated_plan_rejects_unknown_lineage_step() -> None:
    plan = _plan(_step("s1"), _step("s2", "s1", vendor=LineageRef(step_id="s1", path="/id")))
    plan.steps[1].proposal.arguments["vendor"] = LineageRef(step_id="missing", path="/id")
    with pytest.raises(ValidationError, match="lineage step 'missing' is not in depends_on"):
        ActionPlan.model_validate(plan)
    later = _plan(_step("s1"), _step("s2", "s1"), _step("s3"))
    later.steps[1].proposal.arguments["deep"] = ({"x": [LineageRef(step_id="s3", path="")]},)
    with pytest.raises(ValidationError, match="lineage step 's3' is not in depends_on"):
        ActionPlan.model_validate(later)
    hidden = _plan(_step("s1"), _step("s2", "s1"))
    hidden.steps[1].proposal.arguments["tags"] = frozenset({LineageRef(step_id="s9", path="")})
    with pytest.raises(ValidationError, match="lineage step 's9' is not in depends_on"):
        ActionPlan.model_validate(hidden)


def test_model_construct_plan_fails_validation_on_revalidate() -> None:
    def constructed(step_id: str, *depends_on: str, **arguments: Any) -> PlannedStep:
        return PlannedStep.model_construct(
            step_id=step_id, proposal=_proposal(**arguments), depends_on=depends_on
        )

    def plan_of(*steps: PlannedStep) -> ActionPlan:
        return ActionPlan.model_construct(
            plan_id="plan_1", task_id="purchase_order", task_version="1", steps=steps
        )

    literal = plan_of(constructed("s1"), constructed("s2", "s1", v={"$lineage": {}}))
    with pytest.raises(ValidationError, match=r"\$lineage"):
        ActionPlan.model_validate(literal.model_dump())
    with pytest.raises(ValidationError, match=r"\$lineage"):
        ActionPlan.model_validate(literal)
    unknown = plan_of(constructed("s1", v=LineageRef(step_id="s0", path="/id")))
    with pytest.raises(ValidationError, match="lineage step 's0' is not in depends_on"):
        ActionPlan.model_validate(unknown)
    later = plan_of(
        constructed("s1", "s2", v=LineageRef(step_id="s2", path="/id")), constructed("s2")
    )
    with pytest.raises(ValidationError, match="later step 's2'"):
        ActionPlan.model_validate(later)
    with pytest.raises(ValidationError, match="later step 's2'"):
        ActionPlan.model_validate(later.model_dump())
    looping = plan_of(constructed("s1", "s1"))
    with pytest.raises(ValidationError, match="depends on itself"):
        ActionPlan.model_validate(looping)


def test_action_record_plan_fields_default_null() -> None:
    fields: dict[str, Any] = {
        "action_id": "a1",
        "tenant_id": "t1",
        "run_id": "r1",
        "logical_operation_id": "op1",
        "contract_id": "erp.purchase.create.v1",
        "binding_id": "b1",
        "connection_id": "c1",
        "connection_version": 1,
        "credential_subject": "svc",
        "arguments": {},
        "digest": "sha256:x",
        "state": ActionState.PROPOSED,
        "revision": 0,
    }
    action = ActionRecord.model_validate(fields)
    assert action.plan_id is None
    assert action.step_index is None
    linked = ActionRecord.model_validate({**fields, "plan_id": "plan_1", "step_index": 0})
    assert (linked.plan_id, linked.step_index) == ("plan_1", 0)
    with pytest.raises(ValidationError, match="plan_id and step_index"):
        ActionRecord.model_validate({**fields, "plan_id": "plan_1"})
    with pytest.raises(ValidationError):
        ActionRecord.model_validate({**fields, "plan_id": "plan_1", "step_index": -1})


def test_run_record_task_fields_default_null() -> None:
    fields: dict[str, Any] = {
        "run_id": "r1",
        "tenant_id": "t1",
        "requester_id": "u1",
        "task": "free text",
        "state": RunState.CREATED,
        "revision": 0,
        "logical_operation_id": "op1",
        "created_at": "2026-10-18T00:00:00Z",
    }
    run = RunRecord.model_validate(fields)
    assert run.task_id is None
    assert run.task_version is None
    named = RunRecord.model_validate({**fields, "task_id": "purchase_order", "task_version": "1"})
    assert (named.task_id, named.task_version) == ("purchase_order", "1")
    with pytest.raises(ValidationError, match="task_id and task_version"):
        RunRecord.model_validate({**fields, "task_id": "purchase_order"})


def test_contract_records_are_frozen() -> None:
    task = TaskDefinition(
        task_id="t",
        version="1",
        title="T",
        goal_template="g",
        capabilities=("erp.purchase.create.v1",),
        acceptance=AcceptanceSpec(
            required_effects=(RequiredEffect(contract_id="erp.purchase.create.v1"),)
        ),
    )
    ref = LineageRef(step_id="s1", path="/id")
    plan = _plan(_step("s1"))
    step = StepRecord(
        tenant_id="t1",
        run_id="r1",
        step_id="st1",
        sequence=0,
        kind=StepKind.DRIVER_TURN,
        status=StepStatus.STARTED,
        started_at=datetime(2026, 10, 18, tzinfo=UTC),
    )
    capability = CapabilityDescriptor(
        contract_id="erp.purchase.create.v1",
        effect=EffectKind.WRITE,
        input_schema_id="in",
        output_schema_id="out",
    )
    binding = CapabilityBinding(
        binding_id="b1",
        contract_id="erp.purchase.create.v1",
        plugin_id="p",
        plugin_version="1",
        connection_id="c1",
    )
    records: list[tuple[Record, str, object]] = [
        (task, "approval_ttl", timedelta(minutes=1)),
        (task.acceptance, "required_answer", "x"),
        (task.acceptance.required_effects[0], "min_verified", 2),
        (ref, "path", "/other"),
        (plan, "task_id", "other"),
        (plan.steps[0], "depends_on", ("x",)),
        (step, "status", StepStatus.FAILED),
        (StepUsage(), "model_tokens", 1),
        (capability, "risk", "read"),
        (binding, "idempotency", "provider_key"),
    ]
    for record, field, value in records:
        assert type(record).model_config.get("extra") == "forbid"
        with pytest.raises(ValidationError, match="frozen"):
            setattr(record, field, value)
