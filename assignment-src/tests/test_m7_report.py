"""Milestone 7 - charts and the written report.        ./check.sh 7

Code under test:
    agent/charts.py  -> save_chart()
    agent/report.py  -> render_markdown()
"""

from __future__ import annotations

import re

import pytest

from agent import tools
from agent.charts import MAX_POINTS, chart_filename, save_chart
from agent.evidence import (AgentAnswer, ChartFile, Evidence, GraphLookup, PolicyHit, SqlRun)
from agent.report import render_markdown, write_report

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SECTIONS = ["Question", "Answer", "Business rules retrieved", "SQL executed",
            "Knowledge graph lookups", "Charts", "Run details"]


def sample_answer() -> AgentAnswer:
    return AgentAnswer(
        question="Which department has the lowest pass percentage?",
        answer="ME (Mechanical Engineering) has the lowest pass percentage: 90.63 (rule AR-5).",
        evidence=Evidence(
            policies=[PolicyHit(rule_id="AR-2", doc="academic-regulations", section="AR-2 Pass marks",
                                score=0.8577, text="AR-2 Pass marks\n\nTheory 40, Lab 50.", query="pass mark"),
                      PolicyHit(rule_id="AR-5", doc="academic-regulations", section="AR-5 Pass percentage of a group",
                                score=0.7849, text="AR-5 ...", query="pass percentage")],
            sql=[SqlRun(query="DELETE FROM student_performance", status="rejected",
                        error="only SELECT queries are allowed (this is a DELETE statement)"),
                 SqlRun(query="SELECT department, pass_pct FROM x",
                        executed_sql="SELECT sp.department, 90.63 AS pass_percentage FROM student_performance AS sp LIMIT 200",
                        status="ok", columns=["department", "pass_percentage"],
                        rows=[["ME", 90.63], ["CE", 93.13]], row_count=2)],
            graph=[GraphLookup(tool="subject_dependents", args={"subject_code": "ME301"}, status="ok",
                               row_count=6, result=[{"code": "ME401"}])],
            charts=[ChartFile(path="output/charts/pass-percentage-by-department.png",
                              title="Pass percentage by department", kind="bar", points=5)],
        ),
        tools_used=["search_policies", "run_sql", "run_sql", "subject_dependents", "make_chart"],
        model="anthropic/claude-opus-5-5", stop_reason="end_turn", turns=4,
        usage={"input_tokens": 9123, "output_tokens": 456, "total_tokens": 9579}, latency_s=12.34,
    )


# ── charts ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind", ["bar", "line"])
def test_save_chart_writes_a_png(tmp_path, kind):
    title = f"Average percentage by department ({kind})"
    path = save_chart(["CSE", "IT", "CE", "ECE", "ME"], [68.47, 67.19, 64.29, 63.31, 61.76],
                      title=title, x_label="department", y_label="average %", kind=kind, out_dir=tmp_path)
    assert path == tmp_path / chart_filename(title), f"the chart must be saved to `path`, got {path}"
    assert path.is_file(), f"save_chart() returned {path} but did not write it"
    data = path.read_bytes()
    assert data.startswith(PNG_SIGNATURE), "the file is not a PNG"
    assert len(data) > 4000, f"the PNG is only {len(data)} bytes - is anything drawn on it?"


def test_save_chart_creates_the_output_folder(tmp_path):
    target = tmp_path / "does" / "not" / "exist"
    assert save_chart(["a", "b"], [1, 2], title="tiny", out_dir=target).parent == target


def test_save_chart_copes_with_many_long_labels(tmp_path):
    labels = [f"Subject number {i} with a long title" for i in range(MAX_POINTS)]
    path = save_chart(labels, [float(i) for i in range(MAX_POINTS)], title="Many labels", out_dir=tmp_path)
    assert path.read_bytes().startswith(PNG_SIGNATURE)


def test_save_chart_does_not_touch_pyplot_state(tmp_path):
    import matplotlib.pyplot as plt

    open_before = plt.get_fignums()
    save_chart(["a", "b"], [1, 2], title="isolated", out_dir=tmp_path)
    assert plt.get_fignums() == open_before, (
        "save_chart() left a pyplot figure open. Build a matplotlib.figure.Figure directly instead "
        "of using plt.figure()/plt.subplots(): this code runs on a worker thread.")


def test_make_chart_tool_draws_the_query_result(loaded_data, evidence, settings, expected):
    result = tools.make_chart(
        sql="SELECT department, ROUND(AVG(marks * 100.0 / total_marks), 2) AS average_percentage "
            "FROM student_performance GROUP BY department ORDER BY average_percentage DESC",
        label_column="department", value_column="average_percentage",
        title="Checkpoint 7 - average percentage by department")
    assert "chart_path" in result, f"make_chart failed: {result}"
    assert (settings.root / result["chart_path"]).is_file(), f"{result['chart_path']} was not written"
    assert [pair[0] for pair in result["data"]] == [d for d, _ in expected["department_average"]]
    record = evidence.snapshot()
    assert len(record.charts) == 1 and record.charts[0].points == 5
    assert record.sql and record.sql[0].status == "ok", "the chart's query belongs in the SQL evidence too"


# ── report ───────────────────────────────────────────────────────────────────

def test_report_has_every_section_in_order():
    document = render_markdown(sample_answer())
    assert isinstance(document, str), "render_markdown() must return a string"
    headings = re.findall(r"^## (.+)$", document, flags=re.M)
    assert headings == SECTIONS, f"the report needs these level-2 sections in this order:\n  {SECTIONS}\ngot:\n  {headings}"


def test_report_shows_question_answer_and_rules():
    answer = sample_answer()
    document = render_markdown(answer)
    assert answer.question in document and answer.answer in document
    for hit in answer.evidence.policies:
        assert hit.rule_id in document and hit.section in document, f"rule {hit.rule_id} is missing from the report"


def test_report_shows_every_sql_statement_including_refused_ones():
    document = render_markdown(sample_answer())
    assert "```sql" in document, "put each statement in a ```sql fenced block"
    assert "SELECT sp.department, 90.63 AS pass_percentage" in document, (
        "show `executed_sql` - the statement that actually ran - for successful queries")
    assert "| ME | 90.63 |" in document, "show the result rows as a Markdown table (use markdown_table())"
    assert "DELETE FROM student_performance" in document, "a refused statement must still be shown"
    assert "only SELECT queries are allowed" in document, "show WHY a statement was refused"


def test_report_shows_graph_lookups_charts_and_run_details():
    answer = sample_answer()
    document = render_markdown(answer)
    assert "subject_dependents" in document and "ME301" in document, "list each graph lookup with its arguments"
    assert "](charts/pass-percentage-by-department.png)" in document, (
        "report.md lives in output/, so the image link must be `charts/<file>.png`, "
        "not `output/charts/<file>.png`")
    assert answer.model in document, "state which model produced the answer"
    assert "9123" in document and "456" in document, "state the tokens used"


def test_empty_sections_say_so():
    bare = AgentAnswer(question="Hello?", answer="Hello.", evidence=Evidence())
    document = render_markdown(bare)
    headings = re.findall(r"^## (.+)$", document, flags=re.M)
    assert headings == SECTIONS, "every section must appear even when it is empty"
    for title in ("Business rules retrieved", "SQL executed", "Knowledge graph lookups", "Charts"):
        body = document.split(f"## {title}", 1)[1].split("\n## ", 1)[0].strip()
        assert body, f"the empty section '{title}' should contain a line saying nothing was found"


def test_write_report_creates_both_files(tmp_path):
    answer = sample_answer()
    paths = write_report(answer, out_dir=tmp_path)
    assert paths["json"].is_file() and paths["markdown"].is_file()
    assert AgentAnswer.model_validate_json(paths["json"].read_text(encoding="utf-8")) == answer, (
        "results.json must round-trip back into the same AgentAnswer")
    assert paths["markdown"].read_text(encoding="utf-8").startswith("# ")
