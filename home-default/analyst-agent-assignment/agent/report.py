"""The report: one question's answer and evidence, written to disk.

Two files in output/ for every question the CLI answers:

    results.json   the complete AgentAnswer, for programs (and the grader)
    report.md      the same content laid out for a person

They are two renderings of ONE object. Neither adds anything the AgentAnswer
does not contain - a report that says more than the evidence does is no longer
a report of the evidence.
"""

from __future__ import annotations

from pathlib import Path

from services.config import get_settings

from .evidence import AgentAnswer

PREVIEW_ROWS = 15


def markdown_table(columns: list[str], rows: list[list], limit: int = PREVIEW_ROWS) -> str:
    """Render rows as a Markdown table, showing at most `limit` of them.  (PROVIDED)"""
    if not columns:
        return "_no columns_"

    def cell(value) -> str:
        text = "" if value is None else str(value)
        return text.replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(cell(c) for c in columns) + " |",
             "| " + " | ".join("---" for _ in columns) + " |"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows[:limit]]
    if len(rows) > limit:
        lines.append(f"\n_{len(rows) - limit} more row(s) not shown._")
    return "\n".join(lines)


def render_markdown(answer: AgentAnswer) -> str:
    """Lay an AgentAnswer out as a Markdown document.

    The document has these level-2 sections, in this order:

        ## Question
        ## Answer
        ## Business rules retrieved    rule id, section and score of each policy hit
        ## SQL executed                every statement: status, the SQL, a preview of its rows
        ## Knowledge graph lookups     tool, arguments and how many results
        ## Charts                      one Markdown image link per chart
        ## Run details                 model, turns, tokens, time, tools used

    A section with nothing in it still appears, with a line saying so - a
    missing heading and "nothing was retrieved" are different statements.
    """
    # TODO M7-2 ─────────────────────────────────────────────────────────
    # Build the document as a list of lines and "\n".join() it at the end.
    #
    # Everything you need is on `answer`:
    #   answer.question, answer.answer
    #   answer.evidence.policies   -> .rule_id .section .score .doc
    #   answer.evidence.sql        -> .status .executed_sql (or .query when the
    #                                 statement never ran) .error .columns .rows
    #                                 .row_count .truncated
    #   answer.evidence.graph      -> .tool .args .status .row_count .error
    #   answer.evidence.charts     -> .path .title
    #   answer.model .turns .usage .latency_s .tools_used .stop_reason
    #
    #   * Put each SQL statement in a ```sql fenced block and its rows through
    #     markdown_table(). Show REJECTED and FAILED statements too, with their
    #     error - what the agent was stopped from doing belongs in the record.
    #   * Chart paths are stored relative to the assignment folder
    #     ("output/charts/x.png") but report.md itself lives in output/, so the
    #     image link must be relative to that: "charts/x.png".
    #   * Empty sections say so, e.g. "_No policy passages were retrieved._"
    raise NotImplementedError("TODO M7-2 (agent/report.py)")


def write_report(answer: AgentAnswer, out_dir: Path | str | None = None) -> dict[str, Path]:
    """Write results.json and report.md for one answer.  (PROVIDED)

    Returns {"json": path, "markdown": path}.
    """
    out_dir = Path(out_dir) if out_dir else get_settings().output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = out_dir / "results.json", out_dir / "report.md"
    json_path.write_text(answer.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(answer), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}
