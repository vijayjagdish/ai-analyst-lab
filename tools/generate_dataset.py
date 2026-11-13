#!/usr/bin/env python3
"""Generate the assignment's data: three CSVs for PostgreSQL and one Turtle file
for Apache Jena Fuseki.

    python tools/generate_dataset.py            # write the files
    python tools/generate_dataset.py --check    # fail if the committed files differ

Standard library only, so it runs on any machine with Python 3.10+ and in CI
without installing the lab's stack.

The output is DETERMINISTIC: same seed, same bytes. That matters more than it
looks. The answer key, the public test expectations and the hidden test
expectations are all computed from these files, and a student's score must not
depend on which machine generated the dataset. Change SEED (or anything in
campus_data.py) and you must regenerate everything downstream - see the lab
README, "Regenerating the data".

What is deliberately "wrong" with the data
------------------------------------------
Real exports are not clean, and the first task of the assignment is to notice:

  * a few marks are EMPTY      -> the student was absent for that paper
  * a few attendance values are EMPTY -> the register was never entered
  * lab papers are out of 50, theory papers out of 100, so raw marks must never
    be compared or averaged across them

How each of those must be treated is written in the policy documents, not here
and not in the column names. An agent that guesses gets different numbers from
an agent that retrieves the rule - which is the point of the assignment.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import campus_data as cd  # noqa: E402

SEED = 20261112
STUDENTS_PER_DEPT = 48
N_ABSENT = 14               # records with empty marks
N_ATTENDANCE_MISSING = 18   # records with empty attendance

LAB_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = LAB_ROOT / "assignment-src" / "data"
GRAPH_FILE = LAB_ROOT / "platform" / "fuseki" / "data" / "campus.ttl"

NS = "https://kg.cream-collar.com/campus/"


# ── validation of the static curriculum ──────────────────────────────────────

def validate_curriculum() -> None:
    """Fail loudly on an inconsistent curriculum instead of emitting a broken graph."""
    errors: list[str] = []
    dept_codes = {d[0] for d in cd.DEPARTMENTS}
    faculty_slugs = {slug for members in cd.FACULTY.values() for slug, _n, _d in members}

    for code, (name, kind, _difficulty, prereqs, skills) in cd.SUBJECTS.items():
        if len(code) != 5 or not code[2:].isdigit():
            errors.append(f"{code}: subject codes are 2 letters + 3 digits")
            continue
        if cd.department_of(code) not in dept_codes:
            errors.append(f"{code}: unknown department prefix")
        if cd.semester_of(code) not in cd.ALL_SEMESTERS:
            errors.append(f"{code}: semester outside {cd.ALL_SEMESTERS}")
        if (kind == cd.L) != (code[4] == "5"):
            errors.append(f"{code}: index 5 must be the lab, and only index 5")
        for pre in prereqs:
            if pre not in cd.SUBJECTS:
                errors.append(f"{code}: prerequisite {pre} does not exist")
            elif cd.semester_of(pre) >= cd.semester_of(code):
                errors.append(f"{code}: prerequisite {pre} is not from an earlier semester")
            elif cd.department_of(pre) != cd.department_of(code):
                errors.append(f"{code}: prerequisite {pre} is in another department")
        for skill in skills:
            if skill not in cd.SKILLS:
                errors.append(f"{code}: unknown skill {skill}")
        if not name.strip():
            errors.append(f"{code}: empty name")

    for dept in dept_codes:
        for semester in cd.ALL_SEMESTERS:
            n = sum(1 for c in cd.SUBJECTS
                    if cd.department_of(c) == dept and cd.semester_of(c) == semester)
            if n != 5:
                errors.append(f"{dept} semester {semester}: expected 5 subjects, found {n}")

    for slug, (_title, subjects, coordinator, _weeks, _mode, _seats) in cd.REMEDIAL_COURSES.items():
        for subject in subjects:
            if subject not in cd.SUBJECTS:
                errors.append(f"remedial {slug}: unknown subject {subject}")
        if coordinator not in faculty_slugs:
            errors.append(f"remedial {slug}: unknown coordinator {coordinator}")

    for slug, (_title, skills) in cd.CAREER_TRACKS.items():
        for skill in skills:
            if skill not in cd.SKILLS:
                errors.append(f"track {slug}: unknown skill {skill}")

    if errors:
        raise SystemExit("curriculum is inconsistent:\n  " + "\n  ".join(errors))


# ── tabular data (PostgreSQL) ────────────────────────────────────────────────

def build_tables() -> dict[str, tuple[list[str], list[list]]]:
    rng = random.Random(SEED)

    names = [f"{first} {last}" for first in cd.FIRST_NAMES for last in cd.LAST_NAMES]
    rng.shuffle(names)

    students = []
    for dept_code, _dept_name, prefix, _est, _intake, base in cd.DEPARTMENTS:
        for roll in range(1, STUDENTS_PER_DEPT + 1):
            ability = rng.gauss(0.0, 1.0)
            # Diligence drives attendance. Correlated with ability (rho 0.55) so
            # low marks and low attendance tend to travel together, as they do
            # in real cohorts, without being the same signal.
            diligence = 0.55 * ability + math.sqrt(1 - 0.55 ** 2) * rng.gauss(0.0, 1.0)
            students.append({
                "student_id": f"{prefix}{cd.COHORT_YEAR}{roll:03d}",
                "student_name": names.pop(),
                "department": dept_code,
                "base": base,
                "ability": ability,
                "diligence": diligence,
            })

    records = []
    for student in students:
        for semester in cd.DATA_SEMESTERS:
            for code, (_name, kind, difficulty, _pre, _skills) in cd.SUBJECTS.items():
                if cd.department_of(code) != student["department"] or cd.semester_of(code) != semester:
                    continue
                total = 100 if kind == cd.T else 50
                pct = student["base"] + difficulty + 11.0 * student["ability"] + rng.gauss(0.0, 7.5)
                pct = min(99.0, max(4.0, pct))
                attendance = 83.0 + 6.5 * student["diligence"] + rng.gauss(0.0, 5.5)
                records.append({
                    "student_id": student["student_id"],
                    "student_name": student["student_name"],
                    "department": student["department"],
                    "semester": semester,
                    "subject": code,
                    "marks": int(round(pct / 100.0 * total)),
                    "total_marks": total,
                    "attendance": int(round(min(100.0, max(38.0, attendance)))),
                })

    # Absentees come from the low-attendance end: a student who skipped classes
    # is the one who skips the paper. Missing registers are simply random.
    by_attendance = sorted(range(len(records)), key=lambda i: (records[i]["attendance"], i))
    absent = set(rng.sample(by_attendance[:160], N_ABSENT))
    remaining = [i for i in range(len(records)) if i not in absent]
    unrecorded = set(rng.sample(remaining, N_ATTENDANCE_MISSING))
    for i in absent:
        records[i]["marks"] = None
    for i in unrecorded:
        records[i]["attendance"] = None

    performance_cols = ["student_id", "student_name", "department", "semester",
                        "subject", "marks", "total_marks", "attendance"]
    performance_rows = [[r[c] for c in performance_cols] for r in records]

    subject_cols = ["subject", "subject_name", "department", "semester", "credits", "subject_type"]
    subject_rows = []
    for code, (name, kind, _difficulty, _pre, _skills) in cd.SUBJECTS.items():
        if cd.semester_of(code) not in cd.DATA_SEMESTERS:
            continue    # future semesters live in the knowledge graph only
        subject_rows.append([code, name, cd.department_of(code), cd.semester_of(code),
                             credits_of(code), kind])

    department_cols = ["department", "department_name", "hod_name", "established_year", "intake"]
    department_rows = [[code, name, cd.FACULTY[code][0][1], est, intake]
                       for code, name, _prefix, est, intake, _base in cd.DEPARTMENTS]

    return {
        "student_performance.csv": (performance_cols, performance_rows),
        "subject_details.csv": (subject_cols, subject_rows),
        "department_details.csv": (department_cols, department_rows),
    }


def credits_of(code: str) -> int:
    index = int(code[4])
    return 2 if index == 5 else (4 if index <= 2 else 3)


def to_csv(columns: list[str], rows: list[list]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        # None -> an empty, UNQUOTED field. PostgreSQL's COPY ... CSV reads that
        # as NULL; pandas reads it as NaN. A quoted "" would be an empty string.
        writer.writerow(["" if value is None else value for value in row])
    return buffer.getvalue()


# ── knowledge graph (Apache Jena) ────────────────────────────────────────────

def turtle_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_graph() -> str:
    out: list[str] = []
    w = out.append

    w(f"# {cd.COLLEGE} ({cd.COLLEGE_SHORT}) - curriculum knowledge graph.")
    w("# GENERATED by tools/generate_dataset.py from tools/campus_data.py. Do not edit by hand.")
    w("#")
    w("# Loaded read-only into Apache Jena Fuseki as dataset /campus.")
    w("# Subject and department CODES (cc:code) are the join keys to the PostgreSQL tables.")
    w("")
    w(f"@prefix cc:    <{NS}ontology#> .")
    w(f"@prefix dept:  <{NS}department/> .")
    w(f"@prefix subj:  <{NS}subject/> .")
    w(f"@prefix fac:   <{NS}faculty/> .")
    w(f"@prefix skill: <{NS}skill/> .")
    w(f"@prefix track: <{NS}track/> .")
    w(f"@prefix rem:   <{NS}remedial/> .")
    w("@prefix rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .")
    w("@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .")
    w("@prefix owl:   <http://www.w3.org/2002/07/owl#> .")
    w("@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .")
    w("")

    w("# ── Ontology ─────────────────────────────────────────────────────────────")
    classes = [
        ("Department", "An academic department that admits students and offers subjects."),
        ("Subject", "A course in the curriculum, identified by its subject code."),
        ("Faculty", "A member of the teaching staff."),
        ("Skill", "A competency that one or more subjects develop."),
        ("CareerTrack", "A job role described by the skills it requires."),
        ("RemedialCourse", "A short bridge course offered to students who need academic attention."),
    ]
    for name, comment in classes:
        w(f"cc:{name} a owl:Class ; rdfs:label {turtle_string(name)} ; rdfs:comment {turtle_string(comment)} .")
    w("")
    properties = [
        ("code", "owl:DatatypeProperty", None, "xsd:string",
         "Short code. For a Subject or Department this equals the code used in the PostgreSQL tables."),
        ("offeredBy", "owl:ObjectProperty", "cc:Subject", "cc:Department", "The department that runs the subject."),
        ("semester", "owl:DatatypeProperty", "cc:Subject", "xsd:integer", "Semester in which the subject is taught."),
        ("credits", "owl:DatatypeProperty", "cc:Subject", "xsd:integer", "Credit value of the subject."),
        ("subjectType", "owl:DatatypeProperty", "cc:Subject", "xsd:string", "Either Theory or Lab."),
        ("hasPrerequisite", "owl:ObjectProperty", "cc:Subject", "cc:Subject",
         "DIRECT prerequisite. Follow it transitively (hasPrerequisite+) for the full chain."),
        ("taughtBy", "owl:ObjectProperty", "cc:Subject", "cc:Faculty", "The faculty member teaching the subject."),
        ("develops", "owl:ObjectProperty", "cc:Subject", "cc:Skill", "A skill the subject builds."),
        ("memberOf", "owl:ObjectProperty", "cc:Faculty", "cc:Department", "The department a faculty member belongs to."),
        ("headedBy", "owl:ObjectProperty", "cc:Department", "cc:Faculty", "The Head of Department."),
        ("designation", "owl:DatatypeProperty", "cc:Faculty", "xsd:string", "Academic rank."),
        ("email", "owl:DatatypeProperty", "cc:Faculty", "xsd:string", "Contact address."),
        ("establishedYear", "owl:DatatypeProperty", "cc:Department", "xsd:integer", "Year the department was founded."),
        ("requiresSkill", "owl:ObjectProperty", "cc:CareerTrack", "cc:Skill", "A skill the career track needs."),
        ("supports", "owl:ObjectProperty", "cc:RemedialCourse", "cc:Subject", "A subject the remedial course helps with."),
        ("coordinatedBy", "owl:ObjectProperty", "cc:RemedialCourse", "cc:Faculty", "Who runs the remedial course."),
        ("durationWeeks", "owl:DatatypeProperty", "cc:RemedialCourse", "xsd:integer", "Length in weeks."),
        ("mode", "owl:DatatypeProperty", "cc:RemedialCourse", "xsd:string", "Weekend or Evening."),
        ("seatLimit", "owl:DatatypeProperty", "cc:RemedialCourse", "xsd:integer", "Maximum enrolment."),
    ]
    for name, kind, domain, range_, comment in properties:
        parts = [f"cc:{name} a {kind}", f"rdfs:label {turtle_string(name)}"]
        if domain:
            parts.append(f"rdfs:domain {domain}")
        parts.append(f"rdfs:range {range_}")
        parts.append(f"rdfs:comment {turtle_string(comment)}")
        w(" ; ".join(parts) + " .")
    w("")

    w("# ── Departments ──────────────────────────────────────────────────────────")
    for code, name, _prefix, established, _intake, _base in cd.DEPARTMENTS:
        hod_slug = cd.FACULTY[code][0][0]
        w(f"dept:{code} a cc:Department ;")
        w(f"    cc:code {turtle_string(code)} ;")
        w(f"    rdfs:label {turtle_string(name)} ;")
        w(f"    cc:establishedYear {established} ;")
        w(f"    cc:headedBy fac:{hod_slug} .")
    w("")

    w("# ── Faculty ──────────────────────────────────────────────────────────────")
    for dept, members in cd.FACULTY.items():
        for slug, name, designation in members:
            email = slug.replace("-", ".") + "@ccit.example"
            w(f"fac:{slug} a cc:Faculty ;")
            w(f"    rdfs:label {turtle_string(name)} ;")
            w(f"    cc:designation {turtle_string(designation)} ;")
            w(f"    cc:memberOf dept:{dept} ;")
            w(f"    cc:email {turtle_string(email)} .")
    w("")

    w("# ── Skills ───────────────────────────────────────────────────────────────")
    for slug, label in cd.SKILLS.items():
        w(f"skill:{slug} a cc:Skill ; rdfs:label {turtle_string(label)} .")
    w("")

    w("# ── Subjects (semesters 3-6; only 3-4 have marks in PostgreSQL) ──────────")
    for code, (name, kind, _difficulty, prereqs, skills) in cd.SUBJECTS.items():
        teacher_slug = cd.faculty_for(code)[0]
        w(f"subj:{code} a cc:Subject ;")
        w(f"    cc:code {turtle_string(code)} ;")
        w(f"    rdfs:label {turtle_string(name)} ;")
        w(f"    cc:offeredBy dept:{cd.department_of(code)} ;")
        w(f"    cc:semester {cd.semester_of(code)} ;")
        w(f"    cc:credits {credits_of(code)} ;")
        w(f"    cc:subjectType {turtle_string(kind)} ;")
        if prereqs:
            w("    cc:hasPrerequisite " + ", ".join(f"subj:{p}" for p in prereqs) + " ;")
        w("    cc:develops " + ", ".join(f"skill:{s}" for s in skills) + " ;")
        w(f"    cc:taughtBy fac:{teacher_slug} .")
    w("")

    w("# ── Career tracks ────────────────────────────────────────────────────────")
    for slug, (title, skills) in cd.CAREER_TRACKS.items():
        w(f"track:{slug} a cc:CareerTrack ;")
        w(f"    rdfs:label {turtle_string(title)} ;")
        w("    cc:requiresSkill " + ", ".join(f"skill:{s}" for s in skills) + " .")
    w("")

    w("# ── Remedial (bridge) courses ────────────────────────────────────────────")
    for slug, (title, subjects, coordinator, weeks, mode, seats) in cd.REMEDIAL_COURSES.items():
        w(f"rem:{slug} a cc:RemedialCourse ;")
        w(f"    rdfs:label {turtle_string(title)} ;")
        w("    cc:supports " + ", ".join(f"subj:{s}" for s in subjects) + " ;")
        w(f"    cc:coordinatedBy fac:{coordinator} ;")
        w(f"    cc:durationWeeks {weeks} ;")
        w(f"    cc:mode {turtle_string(mode)} ;")
        w(f"    cc:seatLimit {seats} .")
    w("")
    return "\n".join(out)


# ── reporting ────────────────────────────────────────────────────────────────

def summarise(tables: dict[str, tuple[list[str], list[list]]]) -> list[str]:
    """Headline numbers, and the margins that make the questions unambiguous."""
    cols, rows = tables["student_performance.csv"]
    idx = {name: i for i, name in enumerate(cols)}
    kind = {code: spec[1] for code, spec in cd.SUBJECTS.items()}

    def pct(row):
        return None if row[idx["marks"]] is None else row[idx["marks"]] * 100.0 / row[idx["total_marks"]]

    def passed(row):
        value = pct(row)
        return value is not None and value >= (50.0 if kind[row[idx["subject"]]] == cd.L else 40.0)

    lines = [f"rows={len(rows)}  students={len({r[idx['student_id']] for r in rows})}  "
             f"absent={sum(r[idx['marks']] is None for r in rows)}  "
             f"attendance_missing={sum(r[idx['attendance']] is None for r in rows)}"]

    dept_avg = {}
    for dept in [d[0] for d in cd.DEPARTMENTS]:
        values = [pct(r) for r in rows if r[idx["department"]] == dept and pct(r) is not None]
        dept_avg[dept] = sum(values) / len(values)
    ranked = sorted(dept_avg.items(), key=lambda kv: -kv[1])
    lines.append("dept avg %: " + "  ".join(f"{d}={v:.2f}" for d, v in ranked))

    subject_avg = {}
    for code in {r[idx["subject"]] for r in rows}:
        values = [pct(r) for r in rows if r[idx["subject"]] == code and pct(r) is not None]
        subject_avg[code] = sum(values) / len(values)
    lowest = sorted(subject_avg.items(), key=lambda kv: kv[1])
    lines.append("lowest subject avg %: " + "  ".join(f"{c}={v:.2f}" for c, v in lowest[:3]))

    pass_rate = 100.0 * sum(passed(r) for r in rows) / len(rows)
    low_attendance = sum(1 for r in rows if r[idx["attendance"]] is not None and r[idx["attendance"]] < 75)
    lines.append(f"overall pass %={pass_rate:.2f}  records with attendance<75={low_attendance}")

    # The questions in the assignment name "the highest" and "the lowest". If the
    # top two are within noise, a correct agent and the answer key could disagree
    # after rounding. Refuse to emit such a dataset; pick another seed instead.
    if ranked[0][1] - ranked[1][1] < 0.75:
        raise SystemExit(f"top two departments too close: {ranked[:2]} - choose another SEED")
    if lowest[1][1] - lowest[0][1] < 1.0:
        raise SystemExit(f"two lowest subjects too close: {lowest[:2]} - choose another SEED")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="do not write; exit 1 if the committed files differ from what would be generated")
    args = parser.parse_args()

    validate_curriculum()
    tables = build_tables()
    outputs = {DATA_DIR / name: to_csv(cols, rows) for name, (cols, rows) in tables.items()}
    outputs[GRAPH_FILE] = build_graph()

    for line in summarise(tables):
        print(line)

    if args.check:
        stale = [path for path, text in outputs.items()
                 if not path.is_file() or path.read_text(encoding="utf-8") != text]
        for path in stale:
            print(f"STALE: {path.relative_to(LAB_ROOT)}", file=sys.stderr)
        return 1 if stale else 0

    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        # newline="" so Python does not turn "\n" into "\r\n" on Windows: these
        # files are copied into a Linux image and compared byte-for-byte by --check.
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        print(f"wrote {path.relative_to(LAB_ROOT)}  ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
