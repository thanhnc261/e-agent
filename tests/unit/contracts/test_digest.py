import hashlib
import json
from importlib.resources import files

import pytest
from e_agent.contracts.digest import CanonicalizationError, canonicalize, digest


def _vectors() -> list[dict[str, object]]:
    raw = files("e_agent.contracts").joinpath("golden/digest_vectors.json").read_text("utf-8")
    return json.loads(raw)["vectors"]  # type: ignore[no-any-return]


@pytest.mark.parametrize("vector", _vectors(), ids=lambda v: str(v["name"]))
def test_golden_vectors(vector: dict[str, object]) -> None:
    canonical = canonicalize(vector["input"])
    assert canonical == vector["canonical"]
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert digest(vector["input"]) == f"jcs-sha256-v1:{expected}" == vector["digest"]


def test_key_order_and_whitespace_do_not_change_digest() -> None:
    a = json.loads('{"x": "1", "y": {"b": "2", "a": "3"}}')
    b = json.loads('{"y":{"a":"3","b":"2"},"x":"1"}')
    assert digest(a) == digest(b)


def test_material_change_changes_digest() -> None:
    assert digest({"quantity": "7"}) != digest({"quantity": "8"})


@pytest.mark.parametrize("bad", [{"n": 1}, {"n": 1.5}, [2], {"n": float("nan")}])
def test_numbers_are_rejected(bad: object) -> None:
    with pytest.raises(CanonicalizationError):
        canonicalize(bad)


def test_non_string_keys_and_unknown_types_rejected() -> None:
    with pytest.raises(CanonicalizationError):
        canonicalize({1: "a"})
    with pytest.raises(CanonicalizationError):
        canonicalize({"a": object()})


def test_lone_surrogate_rejected() -> None:
    with pytest.raises(CanonicalizationError):
        canonicalize({"a": "\ud800"})


def test_plan_vectors_are_shared() -> None:
    """The plan vectors (ADR 0025) sit in the shared file, so ui-core's loop checks them too;
    `tests/unit/kernel/test_ir.py` rebuilds each from its plan records."""
    plan = [v for v in _vectors() if v.get("kind") == "plan"]
    print(f"plan vectors in the shared file: {len(plan)}")
    assert len(plan) >= 3
    for vector in plan:
        assert vector["canonical"] == canonicalize(vector["input"])
        assert vector["digest"] == digest(vector["input"])
