"""HIDDEN - data ingestion, checked through figures the student was never shown.

These read the database directly (services.dataset_service.connect is provided
code), so they depend only on Milestone 1: a correct load gives the right
numbers whatever state the SQL guard is in.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services import dataset_service
from services.dataset_service import connect


@pytest.fixture(scope="module")
def expected_hidden() -> dict:
    return json.loads((Path(__file__).parent / "expected_hidden.json").read_text(encoding="utf-8"))


def fetch(sql: str) -> list[tuple]:
    with connect() as conn:
        return conn.execute(sql).fetchall()


def test_hidden_pass_percentages_follow_from_the_loaded_rows(loaded_data, expected_hidden):
    rows = fetch(
        "SELECT sp.department, ROUND(100.0 * COUNT(*) FILTER (WHERE sp.marks * 100.0 / sp.total_marks >= "
        "CASE WHEN sd.subject_type = 'Lab' THEN 50 ELSE 40 END) / COUNT(*), 2) "
        "FROM student_performance sp JOIN subject_details sd ON sd.subject = sp.subject GROUP BY sp.department")
    got = {department: float(value) for department, value in rows}
    for department, value in expected_hidden["department_pass_percentage"]:
        assert got.get(department) == pytest.approx(value, abs=0.011), (
            f"pass percentage of {department} computed from the loaded tables is {got.get(department)}, "
            f"expected {value} - rows were lost, duplicated or altered during the load")


def test_hidden_lowest_subject_average(loaded_data, expected_hidden):
    subject, value = fetch(
        "SELECT subject, ROUND(AVG(marks * 100.0 / total_marks), 2) FROM student_performance "
        "GROUP BY subject ORDER BY 2, 1 LIMIT 1")[0]
    want_subject, want_value = expected_hidden["subject_average_lowest"]
    assert subject == want_subject and float(value) == pytest.approx(want_value, abs=0.011)


def test_hidden_every_student_has_ten_papers(loaded_data):
    odd = fetch("SELECT student_id, count(*) FROM student_performance GROUP BY student_id HAVING count(*) <> 10")
    assert not odd, f"every student sat 10 papers; these did not after the load: {odd[:5]}"


def test_hidden_no_value_was_turned_into_text_or_nan(loaded_data):
    bad = fetch("SELECT count(*) FROM student_performance WHERE marks = 'NaN'::numeric OR attendance = 'NaN'::numeric")[0][0]
    assert bad == 0, f"{bad} numeric values are NaN - an empty field must be NULL, not NaN"
    ranges = fetch("SELECT min(marks), max(marks), min(attendance), max(attendance), "
                   "min(total_marks), max(total_marks) FROM student_performance")[0]
    assert ranges[0] >= 0 and ranges[1] <= 100 and ranges[4] == 50 and ranges[5] == 100, f"value ranges look wrong: {ranges}"


def test_hidden_load_works_from_another_folder(loaded_data, tmp_path, settings):
    """load_dataset(data_dir) must use the folder it is given, not a hard-coded path."""
    for name in ("department_details.csv", "subject_details.csv"):
        (tmp_path / name).write_bytes((settings.data_dir / name).read_bytes())
    lines = (settings.data_dir / "student_performance.csv").read_text(encoding="utf-8").splitlines()
    (tmp_path / "student_performance.csv").write_text("\n".join(lines[:101]) + "\n", encoding="utf-8")
    try:
        counts = dataset_service.load_dataset(tmp_path)
        assert counts["student_performance"] == 100, (
            f"loading a 100-row file from another folder gave {counts} - is data_dir being ignored?")
    finally:
        dataset_service.load_dataset()          # put the full dataset back for the tests that follow
    assert fetch("SELECT count(*) FROM student_performance")[0][0] == 2400


def test_hidden_a_failed_load_changes_nothing(loaded_data, tmp_path, settings):
    """A load that fails half-way must roll back, not leave the tables half-filled."""
    for name in ("department_details.csv", "subject_details.csv"):
        (tmp_path / name).write_bytes((settings.data_dir / name).read_bytes())
    good = (settings.data_dir / "student_performance.csv").read_text(encoding="utf-8").splitlines()
    broken = good[:51] + ["XX24001,Nobody,NOPE,3,ZZ999,10,100,90"]      # violates both foreign keys
    (tmp_path / "student_performance.csv").write_text("\n".join(broken) + "\n", encoding="utf-8")
    with pytest.raises(Exception):  # noqa: B017, PT011
        dataset_service.load_dataset(tmp_path)
    count = fetch("SELECT count(*) FROM student_performance")[0][0]
    assert count == 2400, (
        f"after a load that failed, student_performance holds {count} rows instead of the 2400 it had. "
        "Do the whole load in ONE transaction so a failure rolls everything back.")
