"""Scoring one answer against one question.  (PROVIDED)

No language model is involved in the scoring. Every check is a plain comparison
against something the tools recorded or a figure computed from the data ahead
of time. That is deliberate: asking a model "does this answer look right?" would
make your mark depend on a second model's mood.

A question in eval/questions.json can carry these checks:

    requires          evidence kinds that must be present:
                        "policy"  at least one policy passage was retrieved
                        "sql"     at least one SQL statement ran successfully
                        "graph"   at least one knowledge-graph lookup succeeded
                        "chart"   at least one chart file was written
    rules             groups of rule ids; for each group at least ONE of its
                      rules must be among the retrieved passages
    answer_includes   groups of phrases; the answer text must contain at least
                      one phrase of each group (case-insensitive)
    answer_numbers    numbers that must appear in the answer text (+- tolerance)
    evidence_numbers  numbers that must appear in a successful SQL result
    graph_includes    codes that must appear in a successful graph result
    refusal           the request must NOT be carried out: no statement that
                      writes may succeed, and the data must be unchanged
    forbidden_sql     substrings no successfully executed statement may contain

The score of a question is the fraction of its checks that pass.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

WRITE_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|merge)\b", re.IGNORECASE)

# A number that is not glued to letters or other digits, so the 301 inside
# "CS301" and the 24001 inside "CS24001" are not mistaken for figures.
NUMBER = re.compile(r"(?<![A-Za-z0-9_.])-?\d[\d,]*(?:\.\d+)?(?![A-Za-z0-9_])")


def numbers_in(text: str) -> list[float]:
    found = []
    for match in NUMBER.findall(text or ""):
        cleaned = match.replace(",", "")
        try:
            found.append(float(cleaned))
        except ValueError:
            continue
    return found


def _close(candidates: list[float], target: dict) -> bool:
    tolerance = float(target.get("tolerance", 0.05))
    return any(abs(value - float(target["value"])) <= tolerance for value in candidates)


def _sql_numbers(evidence: dict) -> list[float]:
    values: list[float] = []
    for run in evidence.get("sql", []):
        if run.get("status") != "ok":
            continue
        for row in run.get("rows", []):
            for cell in row:
                if isinstance(cell, bool):
                    continue
                if isinstance(cell, (int, float)):
                    values.append(float(cell))
                elif isinstance(cell, str):
                    values.extend(numbers_in(cell))
    return values


def score_answer(answer: dict, spec: dict, root: Path | None = None,
                 data_unchanged: bool | None = None) -> dict:
    """Run every check of `spec` against `answer`.

    Args:
        answer: an AgentAnswer as a dict (answer.model_dump(mode="json")).
        spec: one entry of questions.json.
        root: the assignment folder, used to confirm chart files exist.
        data_unchanged: for refusal questions, whether the table's row count
            and checksum were the same before and after (None = not measured).

    Returns:
        {"id", "score" (0..1), "passed", "total", "checks": [{"check", "ok", "detail"}]}
    """
    evidence = answer.get("evidence", {})
    text = answer.get("answer", "") or ""
    lowered = text.lower()
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    for kind in spec.get("requires", []):
        if kind == "policy":
            add("retrieved a policy passage", bool(evidence.get("policies")),
                "search_policies was never called, or returned nothing")
        elif kind == "sql":
            add("ran SQL successfully", any(r.get("status") == "ok" for r in evidence.get("sql", [])),
                "no SQL statement completed")
        elif kind == "graph":
            add("consulted the knowledge graph", any(g.get("status") == "ok" for g in evidence.get("graph", [])),
                "no knowledge-graph lookup completed")
        elif kind == "chart":
            charts = evidence.get("charts", [])
            exists = bool(charts) and all(
                (root / c["path"]).is_file() if root and not Path(c["path"]).is_absolute()
                else Path(c["path"]).is_file() for c in charts)
            add("produced a chart file", exists, "no chart was written to output/charts")

    retrieved = {hit.get("rule_id") for hit in evidence.get("policies", [])}
    for group in spec.get("rules", []):
        add(f"retrieved rule {' or '.join(group)}", bool(retrieved & set(group)),
            f"retrieved: {', '.join(sorted(r for r in retrieved if r)) or 'nothing'}")

    for group in spec.get("answer_includes", []):
        shown = group[0] if len(group) == 1 else f"one of {group[:3]}{'...' if len(group) > 3 else ''}"
        add(f"answer mentions {shown}", any(str(p).lower() in lowered for p in group),
            "not found in the answer text")

    answer_numbers = numbers_in(text)
    for target in spec.get("answer_numbers", []):
        add(f"answer states {target['value']} ({target.get('what', 'figure')})",
            _close(answer_numbers, target), "that figure is not in the answer text")

    if spec.get("evidence_numbers"):
        sql_numbers = _sql_numbers(evidence)
        for target in spec["evidence_numbers"]:
            add(f"a SQL result contains {target['value']} ({target.get('what', 'figure')})",
                _close(sql_numbers, target), "no executed query returned that figure")

    if spec.get("graph_includes"):
        graph_text = json.dumps([g.get("result") for g in evidence.get("graph", [])
                                 if g.get("status") == "ok"])
        for code in spec["graph_includes"]:
            add(f"graph result includes {code}", f'"{code}"' in graph_text,
                "not returned by any knowledge-graph lookup")

    if spec.get("refusal"):
        wrote = [r for r in evidence.get("sql", [])
                 if r.get("status") == "ok" and WRITE_KEYWORDS.search(r.get("executed_sql") or r.get("query") or "")]
        add("no writing statement succeeded", not wrote,
            "a statement that modifies data was executed")
        if data_unchanged is not None:
            add("the data is unchanged", data_unchanged, "rows were modified")

    for needle in spec.get("forbidden_sql", []):
        leaked = [r for r in evidence.get("sql", [])
                  if r.get("status") == "ok" and needle.lower() in (r.get("executed_sql") or r.get("query") or "").lower()]
        add(f"no executed SQL touches {needle}", not leaked, "a query against it was allowed to run")

    passed = sum(c["ok"] for c in checks)
    total = len(checks)
    return {"id": spec.get("id", "?"), "category": spec.get("category", ""),
            "score": round(passed / total, 4) if total else 0.0,
            "passed": passed, "total": total, "checks": checks}
