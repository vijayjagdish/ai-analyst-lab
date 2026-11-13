# Rubric — AI Analyst Lab

**Trainer only.** The weights below are the ones students see in
`ASSIGNMENT.md`; `scripts/grade.py` implements them (`grade.py --rubric`).

| Area | Marks | What is run | Checks |
|---|---:|---|---:|
| Data ingestion and profiling (M1) | 10 | `test_m1_data` + `test_hidden_data` | 15 |
| SQL validation and safety (M3) | 15 | guard tests in `test_m3_sql` + `test_hidden_sql` | 100 |
| SQL execution (M3) | 10 | execution tests in the same two files | 10 |
| Retrieval of business rules (M4) | 15 | `test_m4_policies` + `test_hidden_policies` | 33 |
| Knowledge graph (M5) | 15 | `test_m5_graph` + `test_hidden_graph` | 39 |
| Agent workflow (M6) | 10 | `test_m6_agent` + `test_hidden_agent` (scripted model) | 19 |
| Charts and report (M7) | 5 | `test_m7_report` | 12 |
| Live agent quality (M2, M8) | 20 | `test_m2_llm` (2 marks) + hidden evaluation questions (18 marks) | 2 + 10 questions |
| **Total** | **100** | pass mark **60** | |

Within an area, marks are proportional to the checks passed. An untouched
starter scores **0 in every area** — no test passes before the student writes
code — and the reference solution scores 100.

## How a submission is graded

```bash
grade.py /path/to/student/analyst-agent-assignment      # one student
grade.py --batch /path/to/all-students --rank           # a cohort
grade.py --offline ...                                  # no gateway key: skip the live 20, score out of 80
grade.py --json ...                                     # for the platform
```

`grade.py` never runs the student's copy of the tests or of any PROVIDED file.
It assembles a fresh copy — pristine starter, the student's ten code files, the
hidden tests — and runs that. Editing a test, the scoring code or
`agent/evidence.py` therefore changes nothing; if a PROVIDED file was modified
the report says so under "Needs a human".

### Where to run it

`grade.py` **executes the student's code** with the credentials of the
workspace it runs in. Give the grader its own resources and nothing else:

```bash
provision_student.py --student grader-1 --format json    # its own database + collection
# launch a TRAINER workspace with that environment and a gateway key reserved for grading
```

It drops and reloads the tables in that database and rebuilds that collection
for every submission, so never point it at resources that hold someone's work,
and grade one submission at a time per database.

Budget: the live part asks 10 hidden questions, up to twice each, per
submission. Measure one run (`grade.py` prints the tokens used) before grading a
cohort, and size the grader key's budget from that.

## What the automated score cannot tell you

- **`REFLECTION.md`.** The grader reports how many of the five questions have
  an answer. Whether an answer shows the student watched their own agent work
  is yours to judge. Question 4 (one change, measured) is the most revealing:
  a student who cannot describe a change and its effect has not done
  Milestone 8, whatever their score.
- **The system prompt.** The tests check that it covers the essentials; the
  live evaluation checks that it works. Neither says whether it is *written
  well*. Read it. Capital letters and "IMPORTANT" everywhere usually mean the
  student was fighting a problem a clearer tool description would have fixed.
- **Tool descriptions.** Same: checked for presence and an example value, not
  for clarity.
- **Whether the code is the student's own.** Hidden tests and hidden questions
  defeat hard-coded answers. They do not detect a copied solution.

## Reading a result

A typical partial submission, and what it says:

| Pattern | Likely meaning |
|---|---|
| High on M1–M5, low on live | The tools work; the prompt or tool descriptions do not steer the model. The Milestone 8 loop was skipped. |
| Guard tests: public pass, hidden fail | The guard blocks the listed statements by pattern instead of by parsing. Look for string matching in `sql_guard.py`. |
| Graph tests: public pass, hidden fail | Queries were written for CS301/CS603 specifically, or `direct` is computed wrongly. |
| Live: correct figures but "rule not retrieved" checks fail | The agent guessed the rule and happened to be right — or was told the rule in the prompt. Check `prompts.py` for rules copied out of the policy documents. |
| Live: P2/H2-style questions wrong by a few points | The lab pass mark (50 %) or the absent rule was not applied. See the table in `ANSWER-KEY.md`. |

Putting the college's rules directly into the system prompt makes the numbers
come out right and defeats the purpose of Milestone 4. The live checks that
require a rule to be *retrieved* exist to catch exactly this.
