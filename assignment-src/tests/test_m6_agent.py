"""Milestone 6 - assemble the agent: tools, system prompt, the agent loop.        ./check.sh 6

Code under test:
    agent/tools.py    -> _execute_sql(), subject_prerequisites, subject_dependents
    agent/prompts.py  -> SYSTEM_PROMPT
    agent/agent.py    -> build_agent(), ask()

No real model is called here. tests/fakes.py supplies a scripted one, so these
tests are free, fast and repeatable - and they exercise your REAL tools against
your real database, vector collection and the knowledge graph.
"""

from __future__ import annotations

import pytest

from agent import tools
from agent.agent import ask, build_agent
from agent.evidence import AgentAnswer
from agent.prompts import SYSTEM_PROMPT
from tests.conftest import table_signature
from tests.fakes import ScriptedModel

TOOL_NAMES = ["career_track_subjects", "find_subject", "make_chart", "run_sql", "search_policies",
              "subject_dependents", "subject_prerequisites", "subject_support_contacts"]

AVERAGE_SQL = ("SELECT department, ROUND(AVG(marks * 100.0 / total_marks), 2) AS avg_pct "
               "FROM student_performance GROUP BY department ORDER BY avg_pct DESC")


# ── the SQL pipeline behind run_sql and make_chart ───────────────────────────

def test_successful_sql_is_returned_and_recorded(loaded_data, evidence, expected):
    result = tools._execute_sql(AVERAGE_SQL)
    assert "error" not in result, f"a valid query came back as an error: {result}"
    assert result["rows"][0][0] == expected["department_average"][0][0]
    runs = evidence.snapshot().sql
    assert len(runs) == 1 and runs[0].status == "ok", (
        "a successful statement must be recorded with EVIDENCE.add_sql(..., status='ok', **result)")
    assert runs[0].query == AVERAGE_SQL, "record the SQL exactly as it was given, in `query`"
    assert runs[0].executed_sql and "LIMIT" in runs[0].executed_sql.upper(), (
        "record what the guard returned in `executed_sql` - that is the statement that really ran")
    assert runs[0].row_count == 5 and runs[0].rows, "record the rows that came back"


def test_refused_sql_becomes_an_error_result_not_an_exception(loaded_data, evidence):
    before = table_signature()
    result = tools._execute_sql("DELETE FROM student_performance WHERE marks < 40")
    assert isinstance(result, dict) and "error" in result, (
        f"a refused statement must come back as {{'error': ...}}, got {result!r}")
    assert result.get("hint"), "add a 'hint' saying what IS allowed - the model acts on it"
    runs = evidence.snapshot().sql
    assert len(runs) == 1 and runs[0].status == "rejected", (
        "a refusal must be recorded too: EVIDENCE.add_sql(query=sql, status='rejected', error=...)")
    assert runs[0].error, "record why it was refused"
    assert table_signature() == before, "the data changed"


def test_failing_sql_becomes_a_one_line_error(loaded_data, evidence):
    result = tools._execute_sql("SELECT no_such_column FROM student_performance")
    assert isinstance(result, dict) and "error" in result, f"a database error must be returned as data, got {result!r}"
    assert "no_such_column" in result["error"], f"keep PostgreSQL's message - it says what is wrong: {result['error']!r}"
    assert "\n" not in result["error"], "keep only the first line of the database error"
    runs = evidence.snapshot().sql
    assert len(runs) == 1 and runs[0].status == "error" and runs[0].executed_sql, (
        "record the failure with status='error' and the SQL that was sent")


# ── tools ────────────────────────────────────────────────────────────────────

def test_all_eight_tools_are_offered_and_described_for_the_model():
    names = sorted(tool.tool_spec["name"] for tool in tools.ALL_TOOLS)
    assert names == TOOL_NAMES, f"ALL_TOOLS should contain {TOOL_NAMES}, got {names}"
    for tool in tools.ALL_TOOLS:
        spec = tool.tool_spec
        description = spec["description"]
        assert "TODO" not in description and len(description) >= 120, (
            f"`{spec['name']}` needs a real description - the docstring is the only thing the model "
            f"knows about the tool. Currently: {description[:80]!r}")
        for name, schema in spec["inputSchema"]["json"]["properties"].items():
            assert schema.get("description"), (
                f"argument `{name}` of `{spec['name']}` has no description. Add it to the docstring's "
                "`Args:` section, with an example value.")


@pytest.mark.parametrize("name", ["subject_prerequisites", "subject_dependents"])
def test_your_tool_descriptions_say_when_to_use_them(name):
    spec = getattr(tools, name).tool_spec
    lowered = spec["description"].lower()
    assert "prerequisite" in lowered or "depend" in lowered, (
        f"the description of `{name}` never mentions prerequisites or dependencies - "
        "how would the model know to reach for it?")
    code_argument = spec["inputSchema"]["json"]["properties"]["subject_code"].get("description", "")
    assert any(ch.isdigit() for ch in code_argument), (
        f"give an example value for `subject_code` in `{name}` (e.g. CS301) - "
        "'the subject code' alone does not tell the model what one looks like")


def test_prerequisite_tools_reach_the_graph_and_record_it(fuseki, evidence, expected):
    before_tools = tools.subject_prerequisites(subject_code="CS603")
    want = [row["code"] for row in expected["graph"]["prerequisites"]["CS603"]["transitive"]]
    assert [row["code"] for row in before_tools.get("results", [])] == want, (
        f"subject_prerequisites('CS603') returned {before_tools!r}; expected the codes {want} under 'results'")
    direct_only = tools.subject_prerequisites(subject_code="CS603", include_indirect=False)
    assert [row["code"] for row in direct_only["results"]] == ["CS503"], (
        "include_indirect=False must map to graph_client.prerequisites(..., transitive=False)")

    after = tools.subject_dependents(subject_code="CS301")
    want_after = [row["code"] for row in expected["graph"]["dependents"]["CS301"]]
    assert [row["code"] for row in after.get("results", [])] == want_after

    lookups = evidence.snapshot().graph
    assert [g.tool for g in lookups] == ["subject_prerequisites", "subject_prerequisites", "subject_dependents"], (
        f"each call must be recorded under the tool's own name, got {[g.tool for g in lookups]}")
    assert lookups[0].args == {"subject_code": "CS603", "include_indirect": True}, (
        f"record the arguments the tool was called with, got {lookups[0].args}")
    assert all(g.status == "ok" for g in lookups)


def test_a_bad_subject_code_is_an_error_result(fuseki, evidence):
    result = tools.subject_dependents(subject_code="not-a-code")
    assert "error" in result, f"a bad code must come back as {{'error': ...}}, got {result!r}"
    assert evidence.snapshot().graph[0].status == "error"


# ── the system prompt ────────────────────────────────────────────────────────

def test_system_prompt_briefs_the_agent():
    lowered = SYSTEM_PROMPT.lower()
    assert len(SYSTEM_PROMPT) >= 900, (
        f"the system prompt is {len(SYSTEM_PROMPT)} characters. One line cannot explain three "
        "data sources, a schema and what a good answer looks like.")
    for table in ("student_performance", "subject_details", "department_details"):
        assert table in lowered, f"the prompt never mentions the table `{table}`"
    assert "polic" in lowered, "the prompt never says when to consult the policy documents"
    assert "graph" in lowered, "the prompt never says when to consult the knowledge graph"
    assert any(p in lowered for p in ("read-only", "read only", "only read")), (
        "the prompt never says the database is read-only for the agent")
    assert "percent" in lowered, "the prompt never says to work in percentages rather than raw marks"


# ── the agent loop ───────────────────────────────────────────────────────────

def test_build_agent_wires_the_three_ingredients():
    model = ScriptedModel([{"text": "ok"}])
    agent = build_agent(model)
    assert agent.model is model, "pass the given model through to Agent(model=...)"
    assert agent.system_prompt == SYSTEM_PROMPT, "the agent must use SYSTEM_PROMPT"
    assert sorted(agent.tool_names) == TOOL_NAMES, f"the agent has the tools {sorted(agent.tool_names)}"


def test_ask_returns_the_answer_with_the_evidence_the_tools_recorded(loaded_data, policy_index, fuseki):
    model = ScriptedModel([
        {"tool": "search_policies", "input": {"query": "pass mark for laboratory papers"}},
        [{"tool": "run_sql", "input": {"sql": AVERAGE_SQL}},
         {"tool": "subject_dependents", "input": {"subject_code": "CS301"}}],
        {"text": "CSE has the highest average percentage: 68.47."},
    ])
    answer = ask("Which department has the highest average percentage?", model=model)

    assert isinstance(answer, AgentAnswer), f"ask() must return an AgentAnswer, got {type(answer).__name__}"
    assert answer.question == "Which department has the highest average percentage?"
    assert answer.answer == "CSE has the highest average percentage: 68.47.", (
        f"the answer text should be the model's final message, stripped. Got {answer.answer!r}")
    assert answer.tools_used[0] == "search_policies" and sorted(answer.tools_used) == [
        "run_sql", "search_policies", "subject_dependents"], f"tools_used is {answer.tools_used}"

    assert "AR-2" in [hit.rule_id for hit in answer.evidence.policies], "the retrieved policy passages are missing"
    assert [run.status for run in answer.evidence.sql] == ["ok"] and answer.evidence.sql[0].rows[0][0] == "CSE"
    assert [g.tool for g in answer.evidence.graph] == ["subject_dependents"]

    assert answer.turns == 3, f"three model calls were made, turns is {answer.turns}"
    assert answer.usage == {"input_tokens": 300, "output_tokens": 60, "total_tokens": 360}, (
        f"usage should total the three calls under input_tokens/output_tokens/total_tokens, got {answer.usage}")
    assert answer.model == "scripted-model" and answer.stop_reason == "end_turn"
    assert answer.latency_s >= 0

    seen = model.tool_results()
    assert any("columns" in result for result in seen), "the model never received the SQL result"


def test_a_write_attempt_is_blocked_recorded_and_the_agent_carries_on(loaded_data):
    before = table_signature()
    model = ScriptedModel([
        {"tool": "run_sql", "input": {"sql": "DELETE FROM student_performance WHERE marks < 40"}},
        {"text": "I cannot change the data - I can only read it."},
    ])
    answer = ask("Delete everyone who failed.", model=model)
    assert table_signature() == before, "rows were deleted"
    assert [run.status for run in answer.evidence.sql] == ["rejected"], (
        f"the attempt must appear in the evidence as rejected, got {[r.status for r in answer.evidence.sql]}")
    assert any("error" in result for result in model.tool_results()), (
        "the model must be TOLD the statement was refused, as a tool result it can read")
    assert answer.answer.startswith("I cannot")


def test_the_turn_limit_stops_a_runaway_agent(loaded_data, monkeypatch):
    from services.config import get_settings

    monkeypatch.setenv("AGENT_MAX_TURNS", "3")
    get_settings(reload=True)
    try:
        model = ScriptedModel([{"tool": "run_sql", "input": {"sql": "SELECT count(*) FROM department_details"}}])
        answer = ask("Keep going forever.", model=model)
    finally:
        monkeypatch.delenv("AGENT_MAX_TURNS")
        get_settings(reload=True)
    assert len(model.calls) == 3, (
        f"with AGENT_MAX_TURNS=3 the model must be called 3 times, it was called {len(model.calls)}. "
        "Pass limits={'turns': settings.agent_max_turns} when calling the agent.")
    assert "limit" in answer.stop_reason, f"stop_reason should report the limit, got {answer.stop_reason!r}"
    assert answer.answer.strip(), "when the limit is hit the answer must say so instead of being empty"


def test_each_question_starts_with_an_empty_record(loaded_data):
    ask("first", model=ScriptedModel([
        {"tool": "run_sql", "input": {"sql": "SELECT count(*) FROM department_details"}}, {"text": "5"}]))
    second = ask("second", model=ScriptedModel([{"text": "nothing to look up"}]))
    assert second.evidence.sql == [] and second.tools_used == [], (
        "evidence from the previous question leaked into this one - call EVIDENCE.reset() in ask()")
