# Assignment — A Grounded AI Data Analyst Agent

## The scenario

CreamCollar Institute of Technology (CCIT) has just published the results of
its 2024 batch: 240 students, five departments, semesters 3 and 4. The academic
office has questions, and they are not all the same kind of question.

- *"Which department has the highest average?"* — a number, from the results.
- *"Which students need academic attention?"* — a number too, but only after
  someone has read what the college means by "academic attention".
- *"What is a student who failed Data Structures at risk of next?"* — not in the
  results at all. It depends on which subjects build on which.
- *"Where do we send them?"* — depends on who runs the bridge course.

Until now a person answered these by reading the rule book, writing SQL, and
looking at the curriculum chart. You are going to build the agent that does it:
one that knows **which source answers which part of a question**, uses each
correctly, and returns its evidence with its answer.

## What makes an answer acceptable

An answer that merely *sounds* right is worth nothing here, because people act
on it. Your agent's answer is acceptable when:

1. **Every figure came out of a tool**, not out of the model's memory.
2. **The college's rules were looked up**, not assumed. They are not the
   obvious ones — that is deliberate. An agent that guesses the pass mark gets
   a believable, wrong number.
3. **The evidence is recorded by the tools.** The SQL that ran, the rows it
   returned, the rule that was retrieved, the graph lookup — written down by the
   code that did it, not narrated by the model afterwards.
4. **Nothing was changed.** The agent reads. A request to delete or update data
   is declined, and could not succeed even if the model tried.

## The milestones

Do them in order; each builds on the last. Each has a checkpoint:
`./check.sh <number>`.

### Milestone 1 — Load and profile the data · `services/dataset_service.py`

Load the three CSV files into **your own PostgreSQL database** and describe
what is in it.

- `load_dataset()` — run `sql/schema.sql`, then stream each CSV in with `COPY`.
- `profile_dataset()` — row counts, distinct counts, missing values per column,
  computed with SQL.

Then **read the profile**. Some marks are missing. Some attendance values are
missing. Papers have different maximum marks. Each of those will matter, and
what to do about each is written in the policy documents — which you have not
indexed yet. Notice the problem now; solve it in Milestone 4.

*Try:* `python -m agent.main --load-data --profile`, then `psql` and look around.

### Milestone 2 — Talk to the model · `services/llm_client.py`

Make one call to the language model through the Bifrost gateway: `chat()`.
Fifteen lines, and the foundation of everything after it. Use
`notebooks/02_first_llm_call.ipynb` to see what a tool call looks like on the
wire before a framework hides it from you.

### Milestone 3 — Safe SQL · `agent/sql_guard.py`, `services/dataset_service.py`

The agent will write SQL. Before any of it runs:

- `validate_sql()` — parse the statement with `sqlglot` and allow only a single
  read-only query over the three tables. The test file lists what must pass and
  what must be refused; it *is* the specification.
- `run_readonly_query()` — execute in a read-only transaction, with a time
  limit and a row limit.

Two layers on purpose. The guard reads the statement; the database enforces the
transaction. Either alone will one day be wrong.

### Milestone 4 — Retrieve the rules · `services/vector_client.py`

Turn `knowledge/policies/*.md` into a searchable index in **your Qdrant
collection**.

- `chunk_markdown()` — one chunk per rule (per `## ` heading).
- `build_index()` — embed every chunk and store it.
- `search()` — embed a question, return the closest rules.

*Try:* `python -m agent.main --build-index`, then in a notebook
`search("what is the pass mark for a lab?")` — and read what comes back. Was
that the pass mark you assumed in Milestone 1?

### Milestone 5 — Query the knowledge graph · `services/graph_client.py`

Read `knowledge/graph/ONTOLOGY.md` first. Then:

- `sparql_select()` — send a SPARQL query over HTTP, parse the JSON result.
- `prerequisites()` — everything a subject depends on, using a property path.
- `dependents()` — everything that depends on a subject.
- `support_contacts()` — the teacher and bridge courses for a subject.

### Milestone 6 — Assemble the agent · `agent/tools.py`, `agent/prompts.py`, `agent/agent.py`

- `_execute_sql()` — the pipeline behind the SQL tools: guard → run → record.
- `subject_prerequisites`, `subject_dependents` — two tools, and their
  docstrings. **The docstring is what the model reads.** It is a prompt.
- `SYSTEM_PROMPT` — the agent's standing instructions.
- `build_agent()`, `ask()` — the Strands agent, and the function that returns
  an answer with its evidence.

The checkpoint uses a scripted stand-in for the model, so it is free and
repeatable while exercising your real tools against the real services.

*Then, for the first time:* `python -m agent.main "Which department has the highest average percentage?"`

### Milestone 7 — Charts and the report · `agent/charts.py`, `agent/report.py`

- `save_chart()` — a bar or line chart, saved as a PNG.
- `render_markdown()` — the report: question, answer, rules retrieved, SQL
  executed (including anything refused), graph lookups, charts, run details.

### Milestone 8 — Measure and improve · `eval/`

```bash
python -m eval.run_eval
```

Nine questions, scored without any model in the loop: did the answer contain
the right figure, was the right rule retrieved, did the SQL return the expected
value, was the data left alone. You will not score 100% the first time.

This milestone *is* the work of building agents: read a failed check, form a
theory about why (a vague tool description? a missing instruction? a rule that
was never retrieved?), change **one** thing, run again, compare. Record what you
tried and what it did in `REFLECTION.md`.

## How you are marked — 100 marks

| Area | Marks | Measured by |
|---|---:|---|
| Data ingestion and profiling (M1) | 10 | checkpoint + hidden tests |
| SQL validation and safety (M3) | 15 | checkpoint + hidden tests — more unsafe statements than you have seen |
| SQL execution (M3) | 10 | checkpoint + hidden tests |
| Retrieval of business rules (M4) | 15 | checkpoint + hidden tests |
| Knowledge graph (M5) | 15 | checkpoint + hidden tests — other subjects than the ones here |
| Agent workflow (M6) | 10 | checkpoint + hidden tests, scripted model |
| Charts and report (M7) | 5 | checkpoint tests |
| Live agent quality (M2, M8) | 20 | your agent, a real model, **questions you have not seen** |
| **Total** | **100** | pass mark: **60** |

Within an area, marks are proportional to the checks passed.

The last row is why memorising the nine public questions does not help: the
graded questions are different. An agent that genuinely looks up the rule and
computes from the data answers a new question as well as an old one. An agent
tuned to nine known answers does not.

`REFLECTION.md` is read by your trainer and discussed with you. It is not
auto-scored.

## Rules

- **Change only the code under `# TODO` markers.** Files and functions marked
  PROVIDED — `services/config.py`, `agent/evidence.py`, `agent/main.py`, and
  everything in `tests/`, `eval/`, `data/`, `knowledge/` and `sql/` — are
  replaced by the originals when your work is graded.
- **Keep the function names and return shapes** given in the docstrings. The
  tests and the grader call them.
- **Do not install packages.** Everything you need is in the image; a package
  you add will not exist where your work is graded.
- **Do not hard-code answers.** The graded questions are not the public ones.
- **Your key, your budget.** The gateway key is yours alone. Do not share it or
  paste it anywhere, and do not commit `.env`.
- Working with classmates on *ideas* is fine. The code you submit is yours.

## Submitting

```bash
./check.sh all                 # every milestone, summarised
python -m eval.run_eval        # your final evaluation run (kept in output/)
./check.sh submit              # packs output/submission.zip and lists what is in it
```

Fill in `REFLECTION.md` first — it goes into the zip. Your work stays in this
workspace; your trainer grades it from here.

## Going further (optional, unmarked)

- Give the agent a memory: store each question and answer in a table of your
  own in PostgreSQL, and let it refer back to earlier ones.
- Add a tool. What question can the three sources answer that the current
  tools cannot reach? Write the tool, describe it, add an evaluation question.
- Compare models. Set `LLM_MODEL` in `.env` to another model your key allows
  and run the evaluation on both. Which checks does the cheaper one fail?
- Trace a run. Strands emits OpenTelemetry spans; export them to the console
  and read the timeline of one question.
