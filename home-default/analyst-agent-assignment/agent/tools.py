"""The tools: the only way the agent can touch anything outside its own head.

A tool is an ordinary Python function with the `@tool` decorator. Strands reads
its NAME, its DOCSTRING and its TYPE HINTS and sends them to the model as the
tool's description. That description is all the model knows about the tool:

    the docstring is a prompt.

A vague docstring gets the tool ignored, or called with the wrong thing in the
wrong argument. Write each one for a reader who cannot see the code.

Three habits every tool here follows:

  * It RECORDS what it did in EVIDENCE (see evidence.py). The report and the
    grader read that record, not the model's description of events.
  * It returns ERRORS AS DATA - a dict with an "error" key - instead of raising.
    The model reads the message and can fix its own call on the next turn. An
    exception would also reach the model, but as a bare string with none of the
    guidance you can put in a result.
  * It is NARROW. `subject_prerequisites("CS603")` cannot be misused the way a
    free-form "run any SPARQL" tool could.

    search_policies            Qdrant      what do the rules say          provided
    run_sql                    PostgreSQL  what are the numbers           Milestone 6
    find_subject               Jena        which subject is meant         provided
    subject_prerequisites      Jena        what does it depend on         Milestone 6
    subject_dependents         Jena        what depends on it             Milestone 6
    subject_support_contacts   Jena        where to refer a student       provided
    career_track_subjects      Jena        subjects behind a career       provided
    make_chart                 PostgreSQL  a picture of a query result    provided
"""

from __future__ import annotations

from strands import tool

from services import dataset_service, graph_client, vector_client
from services.config import get_settings
from services.graph_client import GraphError

from .charts import MAX_POINTS, save_chart
from .evidence import EVIDENCE
from .sql_guard import UnsafeSQLError, validate_sql


# ── Qdrant ───────────────────────────────────────────────────────────────────

@tool
def search_policies(query: str, top_k: int = 4) -> dict:
    """Search the college's policy documents for the rules and definitions that apply to a question.

    The documents are the Academic Regulations, the Attendance Policy, the Student
    Support Policy and the Data Dictionary. Call this BEFORE computing anything that
    depends on a definition: what counts as a pass, how absent students or missing
    attendance are treated, how an average or a pass percentage is calculated, and
    what "academic attention", "at risk", "backlog" or "merit list" mean. This
    college's rules differ from common defaults, so never assume them.

    Args:
        query: what you need to know, in plain words, e.g. "pass mark for laboratory papers".
        top_k: number of passages to return, between 1 and 8.
    """
    EVIDENCE.note_tool("search_policies")
    try:
        hits = vector_client.search(query, k=max(1, min(int(top_k), 8)))
    except Exception as exc:  # noqa: BLE001 - whatever went wrong, the model needs to hear about it
        return {"error": f"policy search failed: {exc}"}
    EVIDENCE.add_policy_hits(query, hits)
    return {"results": [
        {"rule_id": hit["rule_id"], "section": hit["section"], "text": hit["text"], "score": hit["score"]}
        for hit in hits
    ]}


# ── PostgreSQL ───────────────────────────────────────────────────────────────

def _execute_sql(sql: str) -> dict:
    """Guard, run and record one SQL statement.

    Returns the query result ({"columns", "rows", "row_count", "truncated"}), or
    {"error": "..."} when the statement was refused or failed. Never raises.
    Every outcome - success, refusal, failure - is written to EVIDENCE.
    """
    settings = get_settings()

    # TODO M6-1 ─────────────────────────────────────────────────────────
    # The pipeline every piece of model-written SQL goes through:
    #
    #   1. validate_sql(sql, max_rows=settings.sql_max_rows)
    #        raises UnsafeSQLError  ->  EVIDENCE.add_sql(query=sql, status="rejected",
    #                                                    error=str(exc))
    #                                   return {"error": "SQL rejected: ...", "hint": "..."}
    #   2. dataset_service.run_readonly_query(safe_sql)
    #        raises anything        ->  EVIDENCE.add_sql(query=sql, executed_sql=safe_sql,
    #                                                    status="error", error=...)
    #                                   return {"error": "SQL failed: ..."}
    #   3. success                  ->  EVIDENCE.add_sql(query=sql, executed_sql=safe_sql,
    #                                                    status="ok", **result)
    #                                   return result
    #
    # Record the refusals and failures too. "The agent tried to DELETE and was
    # stopped" is evidence - arguably the most important kind.
    #
    # For a database error keep only the FIRST LINE of the message
    # (str(exc).strip().splitlines()[0]). PostgreSQL's first line says what is
    # wrong ("column "mark" does not exist"); the rest is position markers that
    # cost tokens and help nobody.
    #
    # In the rejection, add a "hint" telling the model what IS allowed. It will
    # act on it.
    raise NotImplementedError("TODO M6-1 (agent/tools.py)")


@tool
def run_sql(sql: str) -> dict:
    """Run one read-only PostgreSQL SELECT against the student performance data and return the rows.

    Tables (codes, not names, in `department` and `subject`):
      student_performance(student_id, student_name, department, semester, subject,
                          marks, total_marks, attendance)   one row per student per paper
      subject_details(subject, subject_name, department, semester, credits, subject_type)
      department_details(department, department_name, hod_name, established_year, intake)

    `marks` and `attendance` can be NULL and `total_marks` is 100 or 50, so compare
    percentages (marks * 100.0 / total_marks), never raw marks. Do the aggregation,
    filtering and sorting in SQL and return a small result; at most 200 rows come
    back. Only SELECT is permitted - anything that writes is refused.

    Args:
        sql: a single SELECT statement in PostgreSQL syntax.
    """
    EVIDENCE.note_tool("run_sql")
    return _execute_sql(sql)


@tool
def make_chart(sql: str, label_column: str, value_column: str, title: str, kind: str = "bar") -> dict:
    """Draw a chart from the result of a SQL query and save it as a PNG file.

    The chart is drawn directly from the rows the query returns, so the numbers in
    it are the database's numbers. Use it when the user asks for a chart, plot,
    graph or visual comparison. The query follows the same rules as run_sql.

    Args:
        sql: a SELECT returning one row per bar or point (aggregate in SQL; at most 30 rows are drawn).
        label_column: the result column to use for the labels on the x axis.
        value_column: the numeric result column to plot on the y axis.
        title: the chart title.
        kind: "bar" (default) or "line".
    """
    EVIDENCE.note_tool("make_chart")
    result = _execute_sql(sql)
    if "error" in result:
        return result
    columns = result["columns"]
    if label_column not in columns or value_column not in columns:
        return {"error": f"label_column and value_column must be among the result columns {columns}"}
    label_at, value_at = columns.index(label_column), columns.index(value_column)
    rows = [row for row in result["rows"] if row[value_at] is not None][:MAX_POINTS]
    if not rows:
        return {"error": "the query returned no rows that can be plotted"}
    try:
        labels = [str(row[label_at]) for row in rows]
        values = [float(row[value_at]) for row in rows]
        path = save_chart(labels, values, title=title, x_label=label_column,
                          y_label=value_column, kind=kind)
    except (TypeError, ValueError, NotImplementedError) as exc:
        return {"error": f"chart could not be drawn: {exc}"}

    root = get_settings().root
    shown = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    EVIDENCE.add_chart(path=shown, title=title, kind=kind, points=len(rows))
    return {"chart_path": shown, "points": len(rows), "data": [list(pair) for pair in zip(labels, values)]}


# ── Apache Jena (knowledge graph) ────────────────────────────────────────────

def _graph_lookup(tool_name: str, args: dict, call) -> dict:
    """Run one knowledge-graph lookup, record it, turn a failure into data.  (PROVIDED)"""
    EVIDENCE.note_tool(tool_name)
    try:
        result = call()
    except (GraphError, NotImplementedError) as exc:
        EVIDENCE.add_graph(tool_name, args, "error", error=str(exc))
        return {"error": str(exc)}
    EVIDENCE.add_graph(tool_name, args, "ok", result=result)
    if isinstance(result, list):
        return {"count": len(result), "results": result}
    return result


@tool
def find_subject(text: str) -> dict:
    """Look up subjects in the curriculum by code or by part of their title.

    Use this to turn a subject NAME into its CODE before calling any other tool:
    titles are not unique (two departments both teach a "Data Structures" paper),
    while codes such as CS301 are. Covers semesters 3 to 6, including the future
    semesters 5 and 6 that have no marks yet.

    Args:
        text: a subject code such as "CS301", or part of a title such as "data structures".
    """
    return _graph_lookup("find_subject", {"text": text},
                         lambda: graph_client.find_subjects(text))


# TODO M6-2 ─────────────────────────────────────────────────────────────
# Write the two prerequisite tools. The work is already done in
# services/graph_client.py; a tool is the thin, well-described wrapper that lets
# the model reach it. Model them on find_subject above and
# subject_support_contacts below:
#
#     return _graph_lookup("<tool name>", {<the arguments>},
#                          lambda: graph_client.<function>(...))
#
#   subject_prerequisites(subject_code, include_indirect=True)
#       -> graph_client.prerequisites(subject_code, transitive=include_indirect)
#   subject_dependents(subject_code)
#       -> graph_client.dependents(subject_code)
#
# Then write each DOCSTRING as if the model had never seen this project,
# because it has not. A good one answers three questions:
#   * what comes back, in plain words;
#   * WHEN to reach for it - which kinds of question it answers. For
#     subject_dependents that is "what is at risk next for a student who has
#     not passed this subject", which nobody would guess from the name;
#   * what each argument is, with an example value ("CS301", not "a code").
# Keep the `Args:` section - Strands turns it into the parameter descriptions.
@tool
def subject_prerequisites(subject_code: str, include_indirect: bool = True) -> dict:
    """TODO: describe this tool for the model."""
    raise NotImplementedError("M6-2: implement subject_prerequisites")


@tool
def subject_dependents(subject_code: str) -> dict:
    """TODO: describe this tool for the model."""
    raise NotImplementedError("M6-2: implement subject_dependents")


@tool
def subject_support_contacts(subject_code: str) -> dict:
    """Find where a student who needs academic attention in a subject should be referred.

    Returns the faculty member who teaches the subject and any remedial (bridge)
    courses that support it, with each course's coordinator, duration, mode and seat
    limit. An empty remedial_courses list means no bridge course exists and the
    referral is to the teaching faculty. Use it for "who should they contact",
    "is there a remedial course for X" or "who teaches X".

    Args:
        subject_code: the subject's code, e.g. "CS301". Resolve a title with find_subject first.
    """
    return _graph_lookup("subject_support_contacts", {"subject_code": subject_code},
                         lambda: graph_client.support_contacts(subject_code))


@tool
def career_track_subjects(track_name: str, department: str = "") -> dict:
    """List the skills a career track requires and the subjects that develop those skills.

    Use it for questions such as "which subjects matter for a Data Scientist" or
    "what should a student strengthen for a career in VLSI design". If the track name
    is not recognised, the reply lists the available track names.

    Args:
        track_name: the career track, e.g. "Data Scientist".
        department: optional department code such as "CSE" to keep only that department's subjects.
    """
    return _graph_lookup(
        "career_track_subjects", {"track_name": track_name, "department": department},
        lambda: graph_client.career_track(track_name, department or None),
    )


ALL_TOOLS = [
    search_policies,
    run_sql,
    make_chart,
    find_subject,
    subject_prerequisites,
    subject_dependents,
    subject_support_contacts,
    career_track_subjects,
]
