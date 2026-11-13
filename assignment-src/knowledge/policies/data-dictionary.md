# Data Dictionary

CreamCollar Institute of Technology (CCIT) — Student Performance Data, Batch 2024.
This document describes the three tables supplied for analysis and how they relate to each other.

## DD-1 Tables and scope

The data covers one cohort, Batch 2024, for the two semesters it has completed: semester 3 and semester 4. There are 240 students, 48 in each of the five departments.

Three tables are supplied: `student_performance` holds one row for each student in each paper; `subject_details` describes each paper; `department_details` describes each department. Semesters 5 and 6 have not been taught yet, so they do not appear in any table.

## DD-2 Table student_performance

One row per student per paper. The combination of `student_id` and `subject` is unique.

- `student_id`: roll number, for example CS24001.
- `student_name`: full name of the student.
- `department`: department code of the student, for example CSE.
- `semester`: 3 or 4.
- `subject`: subject code of the paper, for example CS301.
- `marks`: marks obtained; empty when the student was absent.
- `total_marks`: maximum marks of the paper, 100 or 50.
- `attendance`: attendance percentage in that subject; empty when not recorded.

## DD-3 Table subject_details

One row per paper taught in semesters 3 and 4.

- `subject`: subject code, the key of this table.
- `subject_name`: title of the paper, for example Data Structures.
- `department`: code of the department that offers the paper.
- `semester`: semester in which the paper is taught.
- `credits`: credit value.
- `subject_type`: `Theory` or `Lab`.

Two departments can offer papers with the same or similar titles under different codes, so a paper must always be identified by its code and not by its title alone.

## DD-4 Table department_details

One row per department.

- `department`: department code, the key of this table. The codes are CSE, IT, ECE, ME and CE.
- `department_name`: full name, for example Computer Science and Engineering.
- `hod_name`: name of the Head of Department.
- `established_year`: year the department was founded.
- `intake`: sanctioned number of seats per year.

## DD-5 Keys and joins

`student_performance.subject` refers to `subject_details.subject`, and `student_performance.department` refers to `department_details.department`. Students take only the papers of their own department, so the department of a student and the department offering the paper are always the same in this data.

Subject codes and department codes are also the identifiers used in the curriculum knowledge graph. A subject code obtained from the tables can be looked up in the graph, and the reverse.

## DD-6 Missing values

Two columns can be empty, and each has a defined meaning. An empty `marks` value means the student was absent for the examination; the Academic Regulations state how absent records are treated. An empty `attendance` value means the register has not been verified; the Attendance Policy states how such records are treated. No other column is ever empty.

## DD-7 What is not in the tables

The tables contain results only. They do not contain prerequisites between subjects, the faculty member teaching each subject, the skills a subject develops, career tracks or remedial courses. Those relationships, and the curriculum of semesters 5 and 6, are held in the curriculum knowledge graph.
