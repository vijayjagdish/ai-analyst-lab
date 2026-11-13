# Troubleshooting

Start here:

```bash
python -m agent.main --doctor
```

It prints what is configured (secrets masked) and checks each service in one
line. Everything below is keyed to what it says.

## Is it my code or the platform?

| Symptom | Whose problem |
|---|---|
| `./check.sh env` fails | **Platform.** Tell your trainer; paste the output of `--doctor`. |
| `Not implemented yet: TODO M3-1 (agent/sql_guard.py)` | **Yours** — and it is not an error, it is the to-do list. |
| A checkpoint test fails with an explanation | **Yours.** The message says what is wrong, not just that something is. |
| `--doctor` says `FAIL` for a service | **Platform**, unless you edited `.env`. |

## PostgreSQL

**`connection refused` / `could not translate host name`** — the server is not
reachable from your container. Platform problem.

**`password authentication failed`** — the `PGPASSWORD` in your environment is
not the one the server has. Do not guess; your trainer re-issues it.

**`relation "student_performance" does not exist`** — you have not loaded the
data yet, or loaded it somewhere else. `python -m agent.main --load-data`.

**`permission denied for database`** — you are trying to reach a database that
is not yours. You have exactly one: `echo $PGDATABASE`.

**`cannot execute ... in a read-only transaction`** — that is
`run_readonly_query()` doing its job. If *you* want to write (loading data,
your own tables), use `dataset_service.connect()` directly, not the agent's
query function.

**`canceling statement due to statement timeout`** — the query took longer than
the limit (5 seconds for the agent's tool). Aggregate in SQL instead of pulling
rows; check for a join without a condition.

## Qdrant

**`Collection ... doesn't exist` / 404** — your collection is created by the
platform when your workspace is provisioned. If `--doctor` says it does not
exist, tell your trainer. Your key is not allowed to create collections, by
design.

**`403 Forbidden`** — you asked for a collection that is not yours, or tried to
create or drop one. Check `QDRANT_COLLECTION` in `--doctor`.

**`401` / token expired** — the Qdrant token has a lifetime. Your trainer
re-issues it; nothing in your collection is lost.

**Search returns the wrong rules** — not a platform problem. Is the heading part
of the text you embed? Did you rebuild the index after changing the chunker
(`python -m agent.main --build-index`)? Are there stale points from an earlier
attempt (does `build_index()` clear the collection first)?

**The first search takes a couple of seconds** — the embedding model is loading
into memory. Later calls are fast.

## Apache Jena Fuseki (knowledge graph)

**`HTTP 400 ... Parse error`** — your SPARQL has a syntax error; Fuseki's
message gives the line and column. Most common: a missing `.` between triple
patterns, a missing prefix, or unbalanced braces in an f-string (`{{` and `}}`
are literal braces inside an f-string).

**`HTTP 404`** — wrong URL. The query endpoint is `$FUSEKI_URL/campus/sparql`.

**`HTTP 415` / `HTTP 400 ... No 'query=' parameter`** — you sent an update, or
sent the query under the wrong form field. The graph is read-only and the field
is named `query`.

**`SERVICE execution disabled`** — federated queries are switched off on the
shared server. You do not need them.

**An empty result that should not be empty** — check the prefix IRIs
character by character against `knowledge/graph/ONTOLOGY.md`. A wrong prefix is
not an error in SPARQL; it is a different, non-existent thing, and matching
nothing is a valid answer.

## Bifrost gateway (the model)

**`401` / `invalid virtual key`** — the key in `.env` is wrong or was revoked.
Open `.env` (**View → Show Hidden Files**), check `OPENAI_API_KEY`.

**`429`** — you hit your rate limit. Wait a minute. If it is your *budget* that
is exhausted the message says so; ask your trainer.

**`model ... is not allowed for virtual key`** — your key is restricted to
certain models. `--doctor` reports how many models the key can use; set
`LLM_MODEL` in `.env` to one your trainer names.

**`400 ... temperature` (or `top_p`)** — you passed a sampling parameter. The
current Claude models reject them. Remove it.

**Plain chat works but the agent fails or never calls a tool** — run
`./check.sh env` and look at `test_model_can_call_a_tool`. If it fails, the
configured model does not do tool calling through the gateway: tell your
trainer. They may also ask you to set `LLM_STREAM=false` in `.env`.

**The agent stops with "could not finish within 12 steps"** — it kept calling
tools without converging. Read `output/report.md`: usually one tool keeps
returning an error the model cannot recover from. Fix that tool's error message
or description. Raising `AGENT_MAX_TURNS` only makes the same failure cost more.

## Jupyter

**I edited a `.py` file and the notebook still runs the old code** — a running
kernel keeps the modules it has already imported. **Kernel → Restart**, or put
this in the notebook's first cell:

```python
%load_ext autoreload
%autoreload 2
```

**I cannot see `.env`** — **View → Show Hidden Files** in the file browser, or
`nano .env` in a terminal.

**My work disappeared** — only this workspace folder persists across restarts.
Anything saved outside it is gone when the container restarts.
