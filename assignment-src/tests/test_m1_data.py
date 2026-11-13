"""Milestone 1 - load the dataset into PostgreSQL and profile it.        ./check.sh 1

Code under test: services/dataset_service.py -> load_dataset(), profile_dataset()
"""

from __future__ import annotations

import json

import pytest

from services import dataset_service
from services.dataset_service import connect


def fetch(sql: str, params=None) -> list[tuple]:
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def test_every_table_has_the_right_number_of_rows(loaded_data, expected):
    assert loaded_data == expected["tables"], (
        f"load_dataset() returned {loaded_data}, expected {expected['tables']}.\n"
        "Return a dict of table name -> row count, counted AFTER loading.")
    for table, count in expected["tables"].items():
        actual = fetch(f"SELECT count(*) FROM {table}")[0][0]
        assert actual == count, f"{table} holds {actual} rows in the database, expected {count}"


def test_loading_twice_does_not_duplicate_rows(loaded_data, expected):
    again = dataset_service.load_dataset()
    assert again == expected["tables"], (
        f"a second load_dataset() left {again}; it must leave exactly {expected['tables']}.\n"
        "Run the schema file first each time - it drops and recreates the tables.")


def test_absent_students_are_null_not_zero(loaded_data, expected):
    absent = expected["profile"]["missing"]["marks"]
    nulls = fetch("SELECT count(*) FROM student_performance WHERE marks IS NULL")[0][0]
    zeros = fetch("SELECT count(*) FROM student_performance WHERE marks = 0")[0][0]
    assert nulls == absent, (
        f"{nulls} rows have NULL marks, expected {absent}. An empty CSV field must load as NULL "
        f"({zeros} rows have marks = 0 - if that is {absent}, your loader turned 'absent' into "
        "'scored zero', which changes every average).")


def test_unrecorded_attendance_is_null(loaded_data, expected):
    missing = expected["profile"]["missing"]["attendance"]
    nulls = fetch("SELECT count(*) FROM student_performance WHERE attendance IS NULL")[0][0]
    assert nulls == missing, f"{nulls} rows have NULL attendance, expected {missing}"


def test_columns_have_the_types_the_schema_declares(loaded_data):
    rows = fetch(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'student_performance'")
    types = dict(rows)
    wanted = {"marks": "numeric", "attendance": "numeric", "total_marks": "integer",
              "semester": "integer", "student_id": "text", "subject": "text"}
    wrong = {name: types.get(name) for name, kind in wanted.items() if types.get(name) != kind}
    assert not wrong, (
        f"these columns have the wrong type: {wrong}. Create the tables from sql/schema.sql - a "
        "loader that invents its own table (pandas.to_sql does) stores numbers as text or floats.")


def test_text_values_survive_the_load_intact(loaded_data):
    name = fetch("SELECT department_name FROM department_details WHERE department = 'ECE'")
    assert name and name[0][0] == "Electronics and Communication Engineering", (
        f"department ECE loaded as {name!r} - check how the CSV fields are being split")


def test_foreign_keys_are_in_place(loaded_data):
    constraints = fetch(
        "SELECT count(*) FROM information_schema.table_constraints "
        "WHERE table_schema = current_schema() AND table_name = 'student_performance' "
        "AND constraint_type = 'FOREIGN KEY'")[0][0]
    assert constraints == 2, (
        f"student_performance has {constraints} foreign keys, expected 2. Create the tables by "
        "executing sql/schema.sql rather than defining them yourself.")


def test_profile_reports_what_the_database_holds(loaded_data, expected):
    profile = dataset_service.profile_dataset()
    want = expected["profile"]
    assert isinstance(profile, dict), "profile_dataset() must return a dict"
    missing_keys = sorted(set(want) - set(profile))
    assert not missing_keys, f"profile_dataset() is missing the key(s): {missing_keys}"
    for key in ("row_count", "student_count", "subject_count", "department_count",
                "semesters", "columns", "total_marks_values"):
        assert profile[key] == want[key], f"profile[{key!r}] is {profile[key]!r}, expected {want[key]!r}"
    assert profile["missing"] == want["missing"], (
        f"profile['missing'] is {profile['missing']}, expected {want['missing']}.\n"
        "It needs an entry for EVERY column, including the ones with no NULLs.")
    assert profile["mean_percentage"] == pytest.approx(want["mean_percentage"], abs=0.011), (
        f"profile['mean_percentage'] is {profile['mean_percentage']}, expected {want['mean_percentage']}.\n"
        "It is the mean of marks * 100.0 / total_marks - NOT the mean of raw marks, which mixes "
        "papers out of 100 with papers out of 50.")


def test_profile_can_be_written_as_json(loaded_data):
    try:
        json.dumps(dataset_service.profile_dataset())
    except TypeError as exc:
        pytest.fail(f"profile_dataset() returned something JSON cannot encode: {exc}. "
                    "numeric columns arrive as Decimal - convert with float().", pytrace=False)
