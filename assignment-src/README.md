# Build a Grounded AI Data Analyst Agent

You are going to build an AI agent that answers questions about a college's
examination results — and can **prove** every answer.

Ask it *"Which students need academic attention in Discrete Mathematics, what
is at risk for them next, and where should they be sent?"* and it will look up
the college's own definition of "academic attention", count the students with a
SQL query it wrote, walk a knowledge graph to find the subjects that depend on
that one, find the bridge course and its coordinator — and hand back the answer
together with the rule, the query, the rows and the graph lookups behind it.

Nothing to install. Everything is in this container or reachable from it.

## Start here (10 minutes)

Open a terminal (**File → New → Terminal**) — it starts in this folder.

```bash
python -m agent.main --doctor     # are all four services reachable?
./check.sh env                    # is the container healthy?
```

Both must be clean before you write any code. If either is not, it is a
platform problem, not yours: read [TROUBLESHOOTING.md](TROUBLESHOOTING.md),
then tell your trainer.

Then read [ASSIGNMENT.md](ASSIGNMENT.md) — the brief, the milestones and how
you are marked.

## What is where

Your code runs **inside** this container. Four services run **outside** it,
shared by the whole class, each doing one job:

```
                         ┌──────────────── your container ────────────────┐
                         │  JupyterLab · Python 3.12 · Strands Agents SDK │
   you ── browser ─────▶ │                                                │
                         │      agent/  ── tools ──▶  services/           │
                         └───────┬───────────┬───────────┬──────────┬─────┘
                                 │           │           │          │
                      ┌──────────▼──┐ ┌──────▼─────┐ ┌───▼─────┐ ┌──▼──────────┐
                      │   Bifrost   │ │ PostgreSQL │ │ Qdrant  │ │ Apache Jena │
                      │  gateway    │ │            │ │         │ │   Fuseki    │
                      ├─────────────┤ ├────────────┤ ├─────────┤ ├─────────────┤
                      │ the language│ │ the FACTS  │ │the RULES│ │ the         │
                      │ model       │ │ marks,     │ │ policy  │ │RELATIONSHIPS│
                      │             │ │ attendance │ │ text    │ │ prerequisites│
                      ├─────────────┤ ├────────────┤ ├─────────┤ ├─────────────┤
                      │ your own key│ │ your own   │ │ your own│ │ shared,     │
                      │ and budget  │ │ database   │ │collection│ │ read-only   │
                      └─────────────┘ └────────────┘ └─────────┘ └─────────────┘
```

| Question the agent has | Where the answer lives | You build |
|---|---|---|
| *What do the rules say?* — pass marks, absentees, "at risk" | Policy documents, searched in **Qdrant** | Milestone 4 |
| *What are the numbers?* — averages, counts, lists | Tables in **PostgreSQL** | Milestones 1, 3 |
| *How are things connected?* — prerequisites, teachers, bridge courses | Knowledge graph in **Apache Jena** | Milestone 5 |
| *What does it all mean?* — choosing sources, explaining | The model, through **Bifrost** | Milestones 2, 6 |

You never hold a real cloud or model credential. The gateway key in `.env`
only works against the gateway, carries your budget, and is the only LLM
credential in this container.

## The folder

```
analyst-agent-assignment/
├── README.md              ← you are here
├── ASSIGNMENT.md          the brief: scenario, milestones, marking
├── TROUBLESHOOTING.md     when something outside your code is broken
├── REFLECTION.md          five questions to answer before you submit
├── check.sh               ./check.sh 3   → milestone 3's checkpoint tests
├── .env                   your keys (created for you; never commit or share)
│
├── data/                  the three CSV files                         (Milestone 1)
├── sql/schema.sql         the tables they load into
├── knowledge/
│   ├── policies/          the college's rules, as Markdown            (Milestone 4)
│   └── graph/ONTOLOGY.md  the knowledge graph's schema                (Milestone 5)
│
├── services/              talking to the four outside services
│   ├── config.py              settings                                  provided
│   ├── llm_client.py          Bifrost        chat()                     Milestone 2
│   ├── dataset_service.py     PostgreSQL     load, profile, query       Milestones 1, 3
│   ├── vector_client.py       Qdrant         chunk, index, search       Milestone 4
│   └── graph_client.py        Jena Fuseki    SPARQL                     Milestone 5
│
├── agent/                 the agent itself
│   ├── sql_guard.py           is this SQL safe to run?                  Milestone 3
│   ├── tools.py               what the model is allowed to do           Milestone 6
│   ├── prompts.py             the system prompt                         Milestone 6
│   ├── agent.py               build_agent(), ask()                      Milestone 6
│   ├── charts.py, report.py   pictures and the written report           Milestone 7
│   ├── evidence.py            the evidence trail                        provided
│   └── main.py                command line                              provided
│
├── eval/                  measuring the agent                          (Milestone 8)
├── notebooks/             scratch space for exploring
├── tests/                 the checkpoint tests behind ./check.sh
└── output/                reports, charts and evaluation results land here
```

In the code, every place you have work to do is marked `# TODO M3-1`. Files
and functions marked **PROVIDED** are finished — read them, use them, leave
them as they are (the grader restores them anyway).

## The loop you will repeat

```bash
./check.sh 3                    # red: read the first failure, it says what is wrong
# ...edit the file it names, find the TODO, write the code...
./check.sh 3                    # green: move on
./check.sh all                  # where am I overall?
```

Checkpoints are **red until you do the milestone**. A checkpoint that passes
before you write anything would not be checking anything.

Once the agent works:

```bash
python -m agent.main "Which department has the highest average percentage?"
python -m eval.run_eval          # score it against the evaluation questions
```

## Three things that will save you an hour each

**Edit `.env`, not the code, to change a setting.** It is read every time, so a
change applies on your next run. In a notebook that is already running, call
`get_settings(reload=True)`.

**`psql` just works.** Type `psql` in a terminal and you are in your own
database: `\dt` lists your tables, `\d student_performance` describes one. The
connection details are the standard `PG*` environment variables.

**The agent costs budget; the tests mostly do not.** `./check.sh 1` to
`./check.sh 7` never call the model — milestone 6 uses a scripted stand-in.
Only `./check.sh 2`, `./check.sh env`, asking a question and the evaluation run
spend tokens. Iterate with `python -m eval.run_eval --only P2` rather than
re-running everything.
