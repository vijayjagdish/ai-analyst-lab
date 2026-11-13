"""HIDDEN - SQL guard and execution, with statements the student has not seen.

Copied into the grading directory's tests/ folder by grade.py. Never shipped in
the student image.

Every statement in ACCEPT is also EXECUTED against PostgreSQL: a guard that
"accepts" a query by mangling it into something that no longer runs is not
accepting it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from agent.sql_guard import UnsafeSQLError, validate_sql
from services import dataset_service
from tests.conftest import table_signature


@pytest.fixture(scope="module")
def expected_hidden() -> dict:
    return json.loads((Path(__file__).parent / "expected_hidden.json").read_text(encoding="utf-8"))

ACCEPT = [
    "SELECT sd.subject_type, ROUND(100.0 * COUNT(*) FILTER (WHERE sp.marks * 100.0 / sp.total_marks >= 40) "
    "/ COUNT(*), 2) FROM student_performance sp JOIN subject_details sd ON sd.subject = sp.subject "
    "GROUP BY sd.subject_type",
    "SELECT student_id, student_name, SUM(COALESCE(marks, 0)) * 100.0 / SUM(total_marks) AS aggregate "
    "FROM student_performance WHERE semester = 4 GROUP BY student_id, student_name "
    "HAVING BOOL_AND(attendance IS NULL OR attendance >= 85) ORDER BY aggregate DESC",
    "SELECT COUNT(*) FROM (SELECT student_id FROM student_performance WHERE marks IS NULL "
    "GROUP BY student_id HAVING COUNT(*) > 1) AS repeated",
    "WITH a AS (SELECT department, AVG(marks * 100.0 / total_marks) AS p FROM student_performance "
    "GROUP BY department), b AS (SELECT MAX(p) AS top FROM a) SELECT a.department FROM a, b WHERE a.p = b.top",
    "SELECT DISTINCT ON (department) department, student_name, marks FROM student_performance "
    "ORDER BY department, marks DESC NULLS LAST",
    "SELECT department, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY marks * 100.0 / total_marks) AS median "
    "FROM student_performance GROUP BY department",
    "SELECT d.department_name, COUNT(DISTINCT sp.student_id) FROM public.department_details d "
    "LEFT JOIN public.student_performance sp ON sp.department = d.department GROUP BY d.department_name",
    "SELECT subject FROM subject_details WHERE semester = 3 EXCEPT "
    "SELECT subject FROM student_performance WHERE marks IS NULL",
    "SELECT student_id, marks, LAG(marks) OVER (PARTITION BY student_id ORDER BY subject) AS previous "
    "FROM student_performance LIMIT 20",
    "SELECT UPPER(student_name), LENGTH(student_name), SUBSTRING(student_id FROM 1 FOR 2) "
    "FROM student_performance WHERE student_name ILIKE '%sharma%'",
    "SELECT department, STDDEV_SAMP(marks * 100.0 / total_marks), MIN(marks), MAX(marks) "
    "FROM student_performance GROUP BY department HAVING COUNT(*) > 10",
    "SELECT sp.subject, sd.subject_name FROM student_performance sp JOIN subject_details sd USING (subject) "
    "WHERE sp.attendance BETWEEN 65 AND 74.99 AND sp.semester IN (3, 4)",
]

REJECT = [
    "SELECT * FROM student_performance; DELETE FROM student_performance",
    "SELECT 1; SELECT 2; SELECT 3",
    "WITH x AS (INSERT INTO department_details VALUES ('ZZ', 'z', 'z', 2000, 1) RETURNING *) SELECT * FROM x",
    "WITH x AS (UPDATE student_performance SET attendance = 100 RETURNING student_id) SELECT COUNT(*) FROM x",
    "MERGE INTO student_performance t USING subject_details s ON t.subject = s.subject "
    "WHEN MATCHED THEN UPDATE SET marks = 0",
    "SELECT * FROM student_performance FOR SHARE",
    "CREATE TEMP TABLE t AS SELECT * FROM student_performance",
    "SELECT student_id INTO TEMP scratch FROM student_performance",
    "ALTER TABLE student_performance DROP COLUMN marks",
    "DROP SCHEMA public CASCADE",
    "SELECT * FROM pg_catalog.pg_roles",
    "SELECT * FROM pg_stat_activity",
    "SELECT usename, passwd FROM pg_shadow",
    "SELECT table_name FROM information_schema.columns",
    "SELECT student_id FROM student_performance UNION SELECT usename FROM pg_user",
    "SELECT * FROM student_performance WHERE student_id IN (SELECT student_id FROM audit_log)",
    "SELECT * FROM student_grades",
    "SELECT * FROM otherdb.public.student_performance",
    "SELECT pg_read_binary_file('/etc/shadow')",
    "SELECT pg_ls_dir('.')",
    "SELECT lo_export(1, '/tmp/x')",
    "SELECT pg_terminate_backend(1234)",
    "SELECT current_setting('server_version')",
    "SELECT txid_current()",
    "SELECT dblink_exec('host=x', 'DROP TABLE y')",
    "SELECT * FROM student_performance WHERE marks > (SELECT pg_sleep(30))",
    "SELECT * FROM student_performance CROSS JOIN LATERAL pg_sleep(1)",
    "SELECT * FROM pg_read_file('/etc/hostname') AS t(line)",
    "COPY (SELECT * FROM student_performance) TO '/tmp/out.csv'",
    "GRANT SELECT ON student_performance TO PUBLIC",
    "VACUUM FULL student_performance",
    "REINDEX TABLE student_performance",
    "LOCK TABLE student_performance IN ACCESS EXCLUSIVE MODE",
    "DO $$ BEGIN DELETE FROM student_performance; END $$",
    "PREPARE p AS SELECT 1",
    "NOTIFY channel, 'x'",
    "BEGIN",
    "ROLLBACK",
]


@pytest.mark.parametrize("sql", ACCEPT)
def test_hidden_guard_accepts_and_the_result_runs(loaded_data, sql):
    try:
        cleaned = validate_sql(sql)
    except UnsafeSQLError as exc:
        pytest.fail(f"a legitimate query was refused ({exc}): {sql}", pytrace=False)
    result = dataset_service.run_readonly_query(cleaned, max_rows=5)
    assert result["columns"], f"the guarded statement returned no columns: {cleaned}"


@pytest.mark.parametrize("sql", REJECT)
def test_hidden_guard_refuses(sql):
    try:
        cleaned = validate_sql(sql)
    except UnsafeSQLError:
        return
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"must raise UnsafeSQLError, not {type(exc).__name__}: {sql}", pytrace=False)
    pytest.fail(f"an unsafe statement was accepted as: {cleaned}", pytrace=False)


def test_hidden_guard_limits_only_the_outer_query():
    cleaned = validate_sql("SELECT * FROM (SELECT * FROM student_performance LIMIT 5000) AS inner_rows", max_rows=200)
    assert re.search(r"\bLIMIT 200\s*$", cleaned.strip(), re.I), f"the outer query needs LIMIT 200: {cleaned}"
    assert "5000" in cleaned, f"the inner LIMIT is the query's own business and must be left alone: {cleaned}"


@pytest.mark.parametrize("limit, kept", [(0, True), (200, True), (201, False), (37, True)])
def test_hidden_guard_limit_boundaries(limit, kept):
    cleaned = validate_sql(f"SELECT student_id FROM student_performance LIMIT {limit}", max_rows=200)
    expected = limit if kept else 200
    assert re.search(rf"\bLIMIT {expected}\b", cleaned, re.I), f"LIMIT {limit} should become LIMIT {expected}: {cleaned}"


# ── execution ────────────────────────────────────────────────────────────────

def test_hidden_query_values_match_the_data(loaded_data, expected_hidden):
    result = dataset_service.run_readonly_query(validate_sql(
        "SELECT sp.department, ROUND(100.0 * COUNT(*) FILTER (WHERE sp.marks * 100.0 / sp.total_marks >= "
        "CASE WHEN sd.subject_type = 'Lab' THEN 50 ELSE 40 END) / COUNT(*), 2) AS pass_percentage "
        "FROM student_performance sp JOIN subject_details sd ON sd.subject = sp.subject "
        "GROUP BY sp.department ORDER BY pass_percentage, sp.department"))
    got = {row[0]: row[1] for row in result["rows"]}
    want = dict(expected_hidden["department_pass_percentage"])
    assert got.keys() == want.keys()
    for department, value in want.items():
        assert got[department] == pytest.approx(value, abs=0.011), (
            f"pass percentage of {department}: {got[department]} (expected {value})")


def test_hidden_nulls_come_back_as_none(loaded_data):
    result = dataset_service.run_readonly_query(
        "SELECT marks, attendance FROM student_performance WHERE marks IS NULL OR attendance IS NULL LIMIT 40")
    assert result["row_count"] == 32, f"14 absent + 18 unrecorded = 32 rows, got {result['row_count']}"
    assert all(row[0] is None or row[1] is None for row in result["rows"])


def test_hidden_truncation_boundary(loaded_data):
    exact = dataset_service.run_readonly_query("SELECT * FROM subject_details", max_rows=50)
    assert exact["row_count"] == 50 and exact["truncated"] is False, (
        "exactly max_rows rows exist: nothing was cut off, so truncated must be False")
    one_short = dataset_service.run_readonly_query("SELECT * FROM subject_details", max_rows=49)
    assert one_short["row_count"] == 49 and one_short["truncated"] is True


def test_hidden_session_cannot_be_switched_to_read_write(loaded_data):
    before = table_signature()
    for statement in ("SET TRANSACTION READ WRITE", "SET default_transaction_read_only = off",
                      "INSERT INTO department_details VALUES ('ZZ', 'z', 'z', 2000, 1)"):
        with pytest.raises(Exception):  # noqa: B017, PT011
            dataset_service.run_readonly_query(statement)
    assert table_signature() == before
    with dataset_service.connect() as conn:
        assert conn.execute("SELECT count(*) FROM department_details").fetchone()[0] == 5


def test_hidden_connections_are_not_leaked(loaded_data):
    with dataset_service.connect() as conn:
        before = conn.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE usename = current_user").fetchone()[0]
    for _ in range(8):
        dataset_service.run_readonly_query("SELECT 1 FROM department_details")
        with pytest.raises(Exception):  # noqa: B017, PT011
            dataset_service.run_readonly_query("SELECT no_such_column FROM department_details")
    with dataset_service.connect() as conn:
        after = conn.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE usename = current_user").fetchone()[0]
    assert after <= before + 1, (
        f"{after - before} connection(s) were left open after 16 queries. Close the connection in a "
        "`finally:` block - a failing query must not leak it (each student has a small connection limit).")
