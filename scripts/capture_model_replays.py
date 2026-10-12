"""Capture public model response parts for fixture CI; never export thinking or tool results."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import qualify_model as harness
from e_agent.adapters.pydantic_ai import PydanticAiDriver, ollama_model
from e_agent.server.bootstrap import build_runtime, tool_specs
from e_agent.server.cli import TASK_PROMPTS
from e_agent.server.profile import load_profile
from pydantic_ai import ModelMessagesTypeAdapter, ModelResponse, TextPart, ToolCallPart
from pydantic_core import to_jsonable_python


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    args.evidence.mkdir(parents=True, exist_ok=True)
    attempts = []
    for task in harness.TASK_CONTRACTS:
        captured = False
        for attempt in range(1, 4):
            before = harness.ollama_meta(args.base_url, args.model)
            profile = load_profile()
            runtime = await build_runtime(
                profile,
                driver_factory=lambda registry, profile=profile: PydanticAiDriver(
                    ollama_model(args.model, args.base_url),
                    tool_specs(registry, profile),
                    guidance=registry.agent_guidance,
                    model_settings={"temperature": 0, "seed": 0},
                ),
            )
            record = await harness._run_trial(
                runtime, "valid", {"task": task, "scenario": "valid"}, time.perf_counter(), task
            )
            after = harness.ollama_meta(args.base_url, args.model)
            record.update(model_before=before, model_after=after)
            attempts.append({"task": task, "attempt": attempt, "passed": record["passed"]})
            (args.evidence / f"{task}-capture-{attempt}.json").write_text(
                json.dumps(record, indent=2, default=str), "utf-8"
            )
            if not record["passed"]:
                continue
            if before.get("model_digest") != after.get("model_digest"):
                raise ValueError("model changed during capture")
            if after.get("context_length") != 32768:
                raise ValueError("capture requires the frozen context length")
            run_id = record["events"][0]["run_id"]
            checkpoint = await runtime.store.load_continuation(runtime.operator.tenant_id, run_id)
            assert checkpoint is not None
            assert checkpoint[1] is not None
            messages = ModelMessagesTypeAdapter.validate_python(checkpoint[1]["messages"])
            responses = []
            for message in messages:
                if not isinstance(message, ModelResponse):
                    continue
                calls = [part for part in message.parts if isinstance(part, ToolCallPart)]
                # Snapshot already strips thinking/tags/provider metadata. Keep only calls,
                # or final public text when no call exists; omit tool-return data entirely.
                parts = calls or [part for part in message.parts if isinstance(part, TextPart)]
                if parts:
                    responses.append(
                        {
                            "kind": "response",
                            "parts": [
                                {
                                    "part_kind": "tool-call",
                                    "tool_name": part.tool_name,
                                    "args": to_jsonable_python(part.args),
                                    "tool_call_id": part.tool_call_id,
                                }
                                if isinstance(part, ToolCallPart)
                                else {"part_kind": "text", "content": part.content}
                                for part in parts
                            ],
                        }
                    )
            replay = {
                "kind": "recorded-public-model-parts-fixture-replay",
                "environment": "synthetic fixture ERP; replay is not live evidence",
                "task": task,
                "prompt": TASK_PROMPTS[task],
                "model_digest": before["model_digest"],
                "context_length": after["context_length"],
                "temperature": 0,
                "seed": 0,
                "pydantic_ai_version": checkpoint[1]["pydantic_ai_version"],
                "expected_contract": harness.TASK_CONTRACTS[task],
                "expected_fixture_writes": record["create_calls"],
                "responses": responses,
            }
            (args.out / f"{task}.json").write_text(json.dumps(replay, indent=2), "utf-8")
            captured = True
            print(f"captured {task}: {len(responses)} public responses", flush=True)
            break
        if not captured:
            (args.evidence / "attempts.json").write_text(json.dumps(attempts, indent=2))
            return 1
    (args.evidence / "attempts.json").write_text(json.dumps(attempts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
