"""The driver's base instructions are pinned to a golden file (PR-32, ENG-EVID-5)."""

from pathlib import Path

from e_agent.adapters.pydantic_ai.driver import BASE_INSTRUCTIONS

GOLDEN = Path(__file__).parent / "golden" / "base_instructions.txt"


def test_base_instructions_match_golden():
    # The golden file is the constant byte for byte; it has no trailing newline.
    golden = GOLDEN.read_bytes().decode("utf-8")
    assert golden, "golden file is empty"
    assert golden == BASE_INSTRUCTIONS, (
        "BASE_INSTRUCTIONS changed. If the change is intended, update "
        f"{GOLDEN.name} in the same commit and re-run the recorded-model replays."
    )
