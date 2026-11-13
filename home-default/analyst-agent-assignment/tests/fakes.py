"""A scripted stand-in for the language model.  (PROVIDED)

The real model is slow, costs money and never says exactly the same thing
twice - three bad properties for a unit test. ScriptedModel implements the
same interface Strands expects from a model, but replays a script YOU give it:

    model = ScriptedModel([
        {"tool": "run_sql", "input": {"sql": "SELECT count(*) FROM student_performance"}},
        {"text": "There are 2400 records."},
    ])
    answer = ask("How many records are there?", model=model)

Turn 1 the "model" asks for run_sql; Strands runs YOUR tool for real, against
your real database; turn 2 the "model" gives its final text. Everything except
the model's choices is the genuine article - which makes this the right way to
test the agent's plumbing: tool wiring, evidence recording, guards and limits.

What it cannot test is whether a real model makes good choices. That is what
the evaluation run (`python -m eval.run_eval`) is for.

A script entry is one assistant turn:
    {"text": "..."}                                  a final answer
    {"tool": "name", "input": {...}}                 one tool call
    [{"tool": ...}, {"tool": ...}]                   several tool calls in one turn
When the script runs out, the last entry is repeated (handy for testing limits).
"""

from __future__ import annotations

import json
from typing import Any

from strands.models.model import Model


class ScriptedModel(Model):
    def __init__(self, script: list) -> None:
        if not script:
            raise ValueError("the script needs at least one turn")
        self.script = list(script)
        self.calls: list[dict] = []          # what Strands sent on each turn, for assertions

    # -- the interface Strands requires -------------------------------------------------
    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> dict:
        return {"model_id": "scripted-model"}

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
        raise NotImplementedError("ScriptedModel does not do structured output")
        yield  # pragma: no cover - makes this an async generator

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.calls.append({
            "messages": json.loads(json.dumps(messages, default=str)),
            "tools": [spec["name"] for spec in (tool_specs or [])],
            "system_prompt": system_prompt,
        })
        index = min(len(self.calls) - 1, len(self.script) - 1)
        turn = self.script[index]
        items = turn if isinstance(turn, list) else [turn]

        yield {"messageStart": {"role": "assistant"}}
        stop_reason = "end_turn"
        for position, item in enumerate(items):
            if "tool" in item:
                stop_reason = "tool_use"
                yield {"contentBlockStart": {"start": {"toolUse": {
                    "name": item["tool"], "toolUseId": f"call_{len(self.calls)}_{position}"}}}}
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(item.get("input", {}))}}}}
            else:
                yield {"contentBlockStart": {"start": {}}}
                yield {"contentBlockDelta": {"delta": {"text": item["text"]}}}
            yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": stop_reason}}
        yield {"metadata": {"usage": {"inputTokens": 100, "outputTokens": 20, "totalTokens": 120},
                            "metrics": {"latencyMs": 1}}}

    # -- helpers for assertions ---------------------------------------------------------
    def tool_results(self) -> list[dict]:
        """Every tool result Strands fed back to the model, parsed from JSON where possible."""
        results = []
        for message in (self.calls[-1]["messages"] if self.calls else []):
            for block in message.get("content", []):
                if "toolResult" in block:
                    for part in block["toolResult"].get("content", []):
                        text = part.get("text", "")
                        try:
                            results.append(json.loads(text))
                        except (TypeError, ValueError):
                            results.append({"text": text})
        return results
