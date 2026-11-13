# AI Analyst Lab — one container, one capstone assignment

A student workspace image and the assignment that runs in it: **build an AI
agent that answers questions about a college's examination results and can
prove every answer.**

The agent has to combine four things, each living in a different service:

| The agent needs… | …which lives in | Why that store |
|---|---|---|
| the **rules** — what counts as a pass, how absentees are treated, what "at risk" means | policy documents, searched in **Qdrant** | unstructured text → semantic search |
| the **facts** — every student's marks and attendance | tables in **PostgreSQL** | numbers → SQL |
| the **relationships** — prerequisites, who teaches what, which bridge course helps | a knowledge graph in **Apache Jena Fuseki** | multi-hop connections → SPARQL |
| **judgement** — which source to use, how to explain the result | a language model, through the **Bifrost** gateway | reasoning |

The rules are deliberately not the obvious ones (lab papers pass at 50 %, not
40 %; absentees count against a pass rate but not an average). An agent that
guesses produces a believable wrong number; one that retrieves the rule gets it
right. That difference is what the assignment teaches and what the grader
measures.

> **Status: created locally. Nothing is built, pushed or deployed.** No docker
> CLI exists on the authoring workstation, so both images are unbuilt; the
> assignment code itself was executed and tested against real PostgreSQL,
> Qdrant and Fuseki servers running as local processes. See
> [What was verified](#what-was-verified).

---

## Inside the container

One image, `ai-analyst-lab`, ~1.5 GB (estimate — unbuilt). Everything a student
needs is pre-installed; they install nothing.

| Purpose | Tool | Version |
|---|---|---|
| Runtime | Python | 3.12 (`python:3.12-slim-bookworm`) |
| Browser IDE | JupyterLab (notebooks + terminal + file editor) | 4.6.6 |
| Agent framework | Strands Agents SDK | 1.64.0 |
| Model access | `openai` SDK, pointed at the gateway | 3.49.0 |
| PostgreSQL | `psycopg` 3 (driver), SQLAlchemy, **`psql`** client 16 | 3.3.8 / 2.1.8 |
| SQL safety | `sqlglot` — parses model-written SQL | 30.31.0 |
| Vector search | `qdrant-client` | 1.20.0 |
| Embeddings | `fastembed` + **BAAI/bge-small-en-v1.5 baked in** (CPU, offline, 384-d) | 0.9.1 |
| Knowledge graph | `httpx` (SPARQL over HTTP), `rdflib` | 0.28.1 / 7.6.0 |
| Data | pandas, NumPy, DuckDB | 3.1.1 / 2.5.4 / 2.0.0 |
| Charts | Matplotlib, Plotly | 3.11.2 / 7.1.0 |
| Validation | Pydantic | 2.14.3 |
| Tests | pytest | 9.2.0 |
| Tracing | OpenTelemetry SDK | 1.45.2 |
| Shell | git, curl, nano | — |
| **The assignment** | starter code with 21 TODOs, 3 CSV files, 5 policy documents, 3 notebooks, checkpoint tests, an evaluation set | — |

Not in the container, on purpose: no database server, no vector store, no JVM,
no model weights beyond the 67 MB embedding model, and **no real cloud or
provider credential**.

## Outside the container

Four shared services. Every student gets the same URLs and their own slice.

| Service | Role | Per student | Who runs it |
|---|---|---|---|
| **Bifrost gateway** | the LLM | a virtual key (budget, rate limit, model allow-list) | already deployed — `ai-lab/bifrost-gateway/` |
| **PostgreSQL 16** | the facts | **their own database** | `platform/` |
| **Qdrant 1.20** | the rules, as vectors | **their own collection** + a token scoped to it | `platform/` |
| **Apache Jena Fuseki 6.2** | the knowledge graph | read access to one shared, read-only graph | `platform/` |

Details, the isolation model and how each claim was tested:
[platform/README.md](platform/README.md).

Also outside, reused unchanged: the workspace operator that launches the
container, EFS for the student's home, and the existing portal/API.

---

## What the student does

Eight milestones, each with a checkpoint (`./check.sh 3`). The student fills in
21 marked TODOs; everything else is provided.

| # | Milestone | Service | The student writes |
|---|---|---|---|
| 1 | Load and profile the data | PostgreSQL | `COPY` the CSVs into their own database; profile it in SQL |
| 2 | Talk to the model | Bifrost | one chat call; see a tool call on the wire |
| 3 | Safe SQL | PostgreSQL | a parser-based guard (`sqlglot`) + read-only, time-limited execution |
| 4 | Retrieve the rules | Qdrant | chunk the policies, embed, index, search |
| 5 | Query the knowledge graph | Jena | SPARQL over HTTP; transitive prerequisites with a property path |
| 6 | Assemble the agent | Strands | tools and their descriptions, the system prompt, `ask()` |
| 7 | Charts and the report | — | a chart from query results; a report of answer + evidence |
| 8 | Measure and improve | Bifrost | run the evaluation set, change one thing, measure again |

The brief students read: [assignment-src/ASSIGNMENT.md](assignment-src/ASSIGNMENT.md).

Marking is 100 points, 80 of them from deterministic tests (public + hidden)
and 20 from the student's agent answering **hidden questions** with the real
model — scored by comparing figures and recorded evidence, never by asking a
model whether the answer looks right. An untouched starter scores 0; the
reference solution scores 100. See [trainer/RUBRIC.md](trainer/RUBRIC.md).

---

## Layout

```
ai-analyst-lab/
├── README.md                    this file
├── Dockerfile                   the STUDENT image
├── requirements.txt             pinned direct dependencies
├── constraints.txt              all 166 resolved packages (linux/x86_64, py3.12)
├── scripts/
│   ├── entrypoint.sh            seed-once, .env, gosu -> jupyter
│   └── grade.py                 the rubric as code            (trainer image only)
│
├── assignment-src/              THE SOURCE OF TRUTH: the complete, working assignment,
│                                with each solution between TODO markers  (= the reference solution)
├── home-default/                what a student gets
│   ├── START-HERE.md
│   └── analyst-agent-assignment/    GENERATED from assignment-src/ - do not edit
│
├── tools/                       generators (standard library only)
│   ├── campus_data.py               the fictional college: curriculum, faculty, skills
│   ├── generate_dataset.py          -> 3 CSV files + the knowledge graph (seeded, deterministic)
│   ├── build_answer_key.py          -> expected figures, evaluation questions, ANSWER-KEY.md
│   ├── build_notebooks.py           -> the three notebooks
│   └── build_assignment.py          -> home-default/ (assignment-src with solutions stripped)
│
├── trainer/                     never in the student image
│   ├── Dockerfile                   the TRAINER image (student image + everything below)
│   ├── RUBRIC.md · ANSWER-KEY.md · answer-key.json
│   ├── verify_answer_key.py         reference SQL vs the independently computed key
│   └── hidden/                      hidden tests + hidden evaluation questions
│
└── platform/                    the services OUTSIDE the container
    ├── README.md
    ├── docker-compose.yml           local stack
    ├── provision_student.py         one student's database + collection + environment
    ├── postgres/ · fuseki/          server configuration
    └── kustomization.yaml · k8s/    for a cluster, later   (NOT APPLIED)
```

## Build and run

Needs a machine with Docker. From this folder:

```bash
docker build -t ai-analyst-lab:v1 .
docker build -f trainer/Dockerfile --build-arg BASE=ai-analyst-lab:v1 -t ai-analyst-lab:v1-trainer .
```

Then bring up the outside services and a workspace — the four commands are in
[platform/README.md](platform/README.md#running-the-three-services-locally).
First thing to run inside the workspace:

```bash
python -m agent.main --doctor     # every service reachable?
./check.sh env                    # includes a real tool-calling round trip through the gateway
```

`./check.sh env` is the test to run before any rollout. Its last case,
`test_model_can_call_a_tool`, is the assumption everything after Milestone 5
rests on: that the configured model, **through the gateway**, does tool calling.

## Environment variables

Injected per student — the output of `platform/provision_student.py`:

| Variable | Meaning |
|---|---|
| `AI_KEY` | Bifrost virtual key (`sk-bf-…`); written into the workspace `.env` on first start |
| `PGHOST` `PGPORT` `PGDATABASE` `PGUSER` `PGPASSWORD` | the student's own database (standard libpq names, so `psql` just works) |
| `QDRANT_URL` `QDRANT_API_KEY` `QDRANT_COLLECTION` | the student's own collection and the token scoped to it |
| `FUSEKI_URL` | the shared knowledge graph; the query endpoint is `$FUSEKI_URL/campus/sparql` |

With defaults baked into the image:

| Variable | Default | Meaning |
|---|---|---|
| `GATEWAY_URL` | `http://bifrost-gateway.ai-lab.svc.cluster.local/v1` | exported as `OPENAI_BASE_URL` |
| `LLM_MODEL` | `anthropic/claude-opus-5-5` | model, as the gateway names it |
| `ROLE` | `student` | `trainer` only has an effect in the trainer image |
| `WORKSPACE_MOUNT_PATH` / `MOUNT_PATH` | `/home/student` | persistent volume path (operator-injected) |
| `JUPYTER_PORT` | `8888` | |

Optional knobs (`LLM_STREAM`, `LLM_MAX_TOKENS`, `AGENT_MAX_TURNS`,
`SQL_MAX_ROWS`, `SQL_TIMEOUT_MS`): see `assignment-src/.env.template`.

## The model

The agent needs a model that does **tool calling**. `gemma` on Bedrock does not
(see `ai-lab/README.md`), so the labs' usual default cannot be used here.

The default is `anthropic/claude-opus-5-5`, the most capable current Opus. It
is one line to change — `LLM_MODEL` at provisioning, or in a student's `.env` —
and the virtual key must allow whichever model you choose:

| Model | Gateway name | Input / output per million tokens |
|---|---|---|
| Claude Opus 5.5 | `anthropic/claude-opus-5-5` | $4.00 / $20.00 |
| Claude Sonnet 5.5 | `anthropic/claude-sonnet-5-5` | $2.00 / $10.00 |
| Claude Haiku 5.5 | `anthropic/claude-haiku-5-5` | $0.10 / $0.50 |

(Anthropic first-party prices as cached 2026-10-06; check the current ones.)

**Cost is your decision, and it is not small at the default.** Nothing here
has been run against a real model, so there is no measured figure. As a
planning estimate only — assuming ~20,000 input and ~2,500 output tokens per
question (several model calls, each re-sending the prompt and tool
definitions) and ~200 questions per student over the assignment:

| Model | Per question | Per student | 50 students |
|---|---|---|---|
| Opus 5.5 | ~$0.13 | ~$26 | ~$1,300 |
| Sonnet 5.5 | ~$0.065 | ~$13 | ~$650 |
| Haiku 5.5 | ~$0.003 | ~$0.65 | ~$33 |

Replace the assumption with a measurement before setting budgets: run the
evaluation once in a real workspace (`python -m eval.run_eval` prints the
tokens used for nine questions) and scale from that. A cheaper model may also
answer worse — the evaluation run tells you by how much, per question.

Two behaviours of the current Claude models that the code already respects:
it never sends `temperature` (rejected), and never forces a tool
(`tool_choice` is left at its default; forcing is rejected). Requests are
`model, messages, tools, stream, stream_options, max_tokens` and nothing else.

## What was verified

Everything below was run on 2026-11-12 against **real servers running as local
processes** (PostgreSQL 16.3, Qdrant 1.20.0, Fuseki 6.2.0 on Temurin 21) with
two provisioned test students, using the exact package versions pinned in
`requirements.txt`.

| What | Result |
|---|---|
| Reference solution, checkpoint tests (offline) | 143 passed |
| Reference solution, hidden tests + checkpoint tests via `grade.py` | 228 / 228 checks → **100 / 100** |
| Untouched starter via `grade.py` | **0 / 100** — no test passes before the student writes code |
| Untouched starter, environment self-test | 24 passed — green from the first second |
| Half-finished submission (M1 + M3 only) | 35 / 80 offline, as the weights predict |
| Answer key vs reference SQL | every figure agrees — computed two independent ways (plain Python on the CSVs; SQL on PostgreSQL) |
| Wrong assumptions give different numbers | checked for six common mistakes — each changes the figure by more than the tolerance |
| SQL guard | 64 unsafe statements refused and 24 legitimate ones accepted (public + hidden lists); the hidden accepted ones are also **executed** on PostgreSQL |
| Policy retrieval | all 21 retrieval test questions (10 public, 11 hidden) return the expected rule in the top 3 |
| Student notebooks | all 16 code cells execute without error |
| Embedding model | loads with every non-local network connection blocked |
| `check.sh` (all modes), `--doctor`, the CLI, `submission.zip` | run end to end |
| Dependency set | resolves for linux/x86_64 + Python 3.12 from wheels only (`constraints.txt`) |
| PostgreSQL apt repository | `bookworm-pgdg` reachable and carries `postgresql-client-16` |
| Per-student isolation; Fuseki read-only | see `platform/README.md` |

### Not verified — read this before a cohort

- **No real language model was ever called.** The gateway was not available
  (and nothing in the cluster was touched to make it so). The agent path was
  exercised two ways instead: with a scripted model inside the real Strands
  loop, and through a stand-in OpenAI-compatible gateway over real HTTP, in
  both streaming and non-streaming modes — against which the reference solution
  scores 9/9 public and 10/10 hidden questions. That proves the plumbing, the
  tools, the scoring and that every question is answerable. It proves
  **nothing** about how well a real model chooses tools or follows the prompt,
  nor that Bifrost translates tool calls for the chosen model correctly.
  `./check.sh env` in a real workspace is the test for the second; one
  `python -m eval.run_eval` is the test for the first.
- **Neither image has been built.** The Dockerfiles follow the patterns of
  `llm-lab` and `sdv-ml-lab`, and their inputs were checked individually (see
  above), but `docker build` has not run.
- **The system prompt and tool descriptions are untuned.** They were written
  carefully and never measured against a real model. Expect to adjust them
  after the first real evaluation run — that is Milestone 8, and the trainer
  should do it once before students do.
- **Token costs are estimates**, as stated above.
- **No load test.** Fifty concurrent students were not simulated.

## Changing things

Everything students see is generated from `assignment-src/` and `tools/`. After
any change, regenerate in this order and re-run the checks:

```bash
python tools/generate_dataset.py     # only if campus_data.py or the seed changed
python tools/build_answer_key.py     # expected figures, questions, ANSWER-KEY.md
python tools/build_notebooks.py
python tools/build_assignment.py     # home-default/ from assignment-src/

# each generator has --check: exit 1 if the committed files are stale
python tools/generate_dataset.py --check && python tools/build_answer_key.py --check \
  && python tools/build_assignment.py --check
```

- **Edit the assignment** in `assignment-src/`, never in `home-default/`. A
  solution sits between `# >>> TODO M3-1`, `# >>> SOLUTION` and
  `# <<< END TODO`; the hints above `SOLUTION` are what the student sees.
- **Changing a policy rule** changes the right answers. Update the rule's
  implementation in `tools/build_answer_key.py`, regenerate, and run
  `trainer/verify_answer_key.py` against a database: it must say the key and
  the reference SQL agree.
- **Regenerating the dataset with another seed** changes every figure. The
  generator refuses a dataset whose "highest" or "lowest" is a near tie. A few
  hidden tests assume the current shape (240 students × 10 papers).
- **Bumping the stack:** change the pin in `requirements.txt`, then
  `uv pip compile requirements.txt --python-version 3.12 --python-platform x86_64-manylinux_2_28 --only-binary :all: --no-header --no-annotate -o constraints.txt`,
  and re-run the tests. Keep `qdrant-client` within one minor version of the
  Qdrant server, and `postgresql-client-NN` on the server's major version.

## Security notes

- Jupyter runs with **no token and no password**, like every image in this
  repo: it expects the platform's authenticating proxy in front of it.
- A student's credentials reach exactly one database, one collection and one
  budgeted gateway key. That boundary was tested (`platform/README.md`).
- Model-written SQL passes a parser-based allow-list **and** runs in a
  read-only transaction with a time limit and a row limit. Either layer alone
  stops every write in the test-suite.
- The hidden tests and the reference solution exist only in the trainer image.
- `grade.py` executes student code with the grader's credentials. Give the
  grader its own database, collection and key (`trainer/RUBRIC.md`).
