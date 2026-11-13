-- Schema for the student performance data.  (PROVIDED - read it, do not edit it.)
--
-- Run by services/dataset_service.load_dataset() against YOUR OWN database.
-- Safe to run again: it drops and recreates the three tables, so a reload
-- always starts from a clean slate.
--
-- Things worth noticing before you write a single query:
--   * `marks` and `attendance` are the only nullable columns. NULL has a
--     defined meaning for each - the policy documents say what.
--   * `total_marks` is 100 for theory papers and 50 for lab papers, so raw
--     marks are not comparable across papers.
--   * `department` and `subject` hold CODES (CSE, CS301). The names live in
--     the two detail tables, and the same codes identify nodes in the
--     knowledge graph.

DROP TABLE IF EXISTS student_performance;
DROP TABLE IF EXISTS subject_details;
DROP TABLE IF EXISTS department_details;

CREATE TABLE department_details (
    department        text PRIMARY KEY,
    department_name   text NOT NULL,
    hod_name          text NOT NULL,
    established_year  integer NOT NULL,
    intake            integer NOT NULL CHECK (intake > 0)
);

CREATE TABLE subject_details (
    subject        text PRIMARY KEY,
    subject_name   text NOT NULL,
    department     text NOT NULL REFERENCES department_details (department),
    semester       integer NOT NULL CHECK (semester BETWEEN 1 AND 8),
    credits        integer NOT NULL CHECK (credits > 0),
    subject_type   text NOT NULL CHECK (subject_type IN ('Theory', 'Lab'))
);

CREATE TABLE student_performance (
    student_id    text NOT NULL,
    student_name  text NOT NULL,
    department    text NOT NULL REFERENCES department_details (department),
    semester      integer NOT NULL CHECK (semester BETWEEN 1 AND 8),
    subject       text NOT NULL REFERENCES subject_details (subject),
    marks         numeric(5, 1) CHECK (marks >= 0),
    total_marks   integer NOT NULL CHECK (total_marks > 0),
    attendance    numeric(5, 1) CHECK (attendance BETWEEN 0 AND 100),
    PRIMARY KEY (student_id, subject),
    CHECK (marks IS NULL OR marks <= total_marks)
);

CREATE INDEX student_performance_department_idx ON student_performance (department);
CREATE INDEX student_performance_subject_idx ON student_performance (subject);
