# Academic Regulations

CreamCollar Institute of Technology (CCIT) — Examination and Assessment Regulations, Batch 2024.
These regulations define how marks are interpreted. Any report, dashboard or automated analysis of student results must follow them.

## AR-1 Percentage of marks

Every paper has its own maximum, recorded in the `total_marks` column. Theory papers are marked out of 100 and laboratory papers out of 50. The percentage for a paper is `marks ÷ total_marks × 100`.

Raw marks must never be compared, ranked or averaged across papers, because a laboratory mark of 40 and a theory mark of 40 mean very different things. Always convert to a percentage first. Percentages in reports are rounded to two decimal places.

## AR-2 Pass marks

The pass mark depends on the type of paper:

- Theory paper: a percentage of at least 40 is a pass.
- Laboratory paper: a percentage of at least 50 is a pass.

A student who scores below the pass mark of a paper has failed that paper. The type of each paper (`Theory` or `Lab`) is recorded in `subject_details.subject_type`.

## AR-3 Absent students

When the `marks` value of a record is empty, the student was absent for that examination. An absent student has not passed the paper.

Absent records are left out when an average percentage is calculated (AR-4), because there is no mark to average. They are still counted in the denominator when a pass percentage is calculated (AR-5), because the student was registered for the paper and did not pass it. An empty mark must never be treated as zero in an average.

## AR-4 Average performance of a group

The average performance (also called "average marks" or "average percentage") of a department, subject, semester or any other group is the arithmetic mean of the percentages (AR-1) of all records in the group, leaving out absent records (AR-3).

It is a plain mean over records. It is not weighted by credits and it is not the mean of raw marks.

## AR-5 Pass percentage of a group

The pass percentage of a group of records is:

`number of records passed ÷ total number of records in the group × 100`

A record is passed according to AR-2. The total includes absent records (AR-3). For example, if 48 students are registered for a paper, 44 pass, 3 fail and 1 is absent, the pass percentage is 44 ÷ 48 × 100 = 91.67.

## AR-6 Letter grades

A letter grade is awarded from the percentage of a paper that has been passed:

- O: 90 and above
- A+: 80 to below 90
- A: 70 to below 80
- B+: 60 to below 70
- B: 50 to below 60
- C: 40 to below 50 (theory papers only, since a laboratory paper needs 50 to pass)

A paper that is not passed is graded F. An absent student is graded AB.

## AR-7 Backlogs and promotion

A paper that a student has not passed, whether failed or absent, is a backlog. Backlogs are counted per student across both semesters of the academic year (semesters 3 and 4 for Batch 2024).

A student who carries more than two backlogs at the end of the academic year is not eligible for promotion to the next year until the number of backlogs is reduced to two or fewer.

## AR-8 Semester aggregate of a student

The semester aggregate of one student is `sum of marks ÷ sum of total_marks × 100`, taken over all papers of that semester. A paper in which the student was absent contributes zero marks and its full `total_marks` to this calculation.

The aggregate describes one student in one semester. It is different from the average performance of a group (AR-4) and the two must not be confused.

## AR-9 Revaluation

A student may apply for revaluation of a theory paper within ten working days of the publication of results by paying the prescribed fee. Laboratory papers are not eligible for revaluation. If the revalued mark differs from the original by more than five marks, the revalued mark replaces the original; otherwise the original mark stands. Results shown in the student performance data are the marks after revaluation.
