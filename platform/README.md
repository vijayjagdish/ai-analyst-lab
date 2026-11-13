# Outside the container — the shared services

The student image holds a workspace and nothing else. Everything the agent
talks to runs **outside** it, once, for the whole class. This folder is those
services: how to run them locally, how to give each student their own slice of
them, and (for later) how they would look on a cluster.

**Nothing here has been deployed anywhere.** The Kubernetes manifests under
`k8s/` were rendered and checked offline only.

## What runs outside, and what each student gets

| Service | Version | What it holds | Each student gets | Enforced by |
|---|---|---|---|---|
| **Bifrost** gateway | 2.4.0 (already deployed — `ai-lab/bifrost-gateway/`) | Access to the language model | A virtual key with a budget, a rate limit and a model allow-list | The gateway |
| **PostgreSQL** | 16 | The facts: marks and attendance | **Their own database** and a login role that owns it | `REVOKE ALL ON DATABASE … FROM PUBLIC`; role is `NOSUPERUSER NOCREATEDB NOCREATEROLE` |
| **Qdrant** | 1.20.0 | The rules: policy text as vectors | **Their own collection** and a token scoped to it | JWT RBAC: `{"access": [{"collection": "<theirs>", "access": "rw"}]}` |
| **Apache Jena Fuseki** | 6.2.0 | The relationships: the curriculum graph | Read access to **one shared graph** | Only query endpoints exist; no update endpoint, no admin API |

So a student holds four things, and each opens exactly one door:

```
AI_KEY                              -> the gateway, up to their budget
PGUSER / PGPASSWORD / PGDATABASE    -> one database
QDRANT_API_KEY / QDRANT_COLLECTION  -> one collection
FUSEKI_URL                          -> a graph nobody can write to
```

Why the graph is shared but the database and the collection are not: students
**write** to the database (they load the CSV files — Milestone 1) and to the
collection (they build the index — Milestone 4), so each needs their own. The
graph is reference data they only read, exactly as an enterprise knowledge
graph would be.

## Provisioning a student

```bash
export PG_ADMIN_URL=postgresql://postgres:<pw>@<host>:5432/postgres
export QDRANT_ADMIN_URL=http://<host>:6333
export QDRANT_ADMIN_KEY=<the Qdrant API key, >= 32 bytes>
export PROVISION_SECRET=<any long random string>
# what the STUDENT's container should use to reach the services:
export STUDENT_PGHOST=... STUDENT_QDRANT_URL=... STUDENT_FUSEKI_URL=... STUDENT_GATEWAY_URL=...

python provision_student.py --student stu-1001 --ai-key sk-bf-... --format json
```

It creates the role and database, creates the (empty) collection, signs the
token, and prints the environment block — `--format json` is the list the
workspace API's `environment` field takes; `--format env` is `KEY=VALUE` lines.
Mint the gateway key with the existing tooling
(`ai-lab/bifrost-gateway/mint-vk.sh`, or `ai-key-api`) and pass it in.

- **Idempotent.** Run it again for the same student and nothing is recreated.
- **No secrets store needed.** The database password is
  `HMAC(PROVISION_SECRET, student id)`, so a re-run — or a relaunched workspace
  — gets the same password without anything having been saved.
- **The Qdrant token expires** (45 days). Re-running issues a fresh one; the
  collection and its contents are untouched.
- `--deprovision --yes` drops the database, the role and the collection.

The student cannot create the collection themselves — a collection-scoped token
may read and write points but not create or drop collections — which is why the
provisioner does it.

## Running the three services locally

Needs a machine with Docker (the authoring workstation has none, so this
compose file is **unrun**; see "What was verified").

```bash
cd platform
cp env.example .env                        # set the secrets
docker compose up -d --build               # postgres, qdrant, fuseki
bash provision-local.sh stu-1001              # database + collection -> student.env
docker compose --profile workspace up -d   # the student's JupyterLab
# open http://localhost:8888/lab
```

`provision-local.sh` needs Python with `psycopg[binary]`, `pyjwt` and `httpx`
on the host. The gateway is not part of the stack: put the existing gateway's
public URL and a virtual key in `.env` (`GATEWAY_URL`, `AI_KEY`).

## What was verified, and how

No Docker was available, so the three servers were run **as native processes**
on the authoring workstation — the same versions, the same configuration files
in this folder — and everything below was observed against them on 2026-11-12.

| Claim | Evidence |
|---|---|
| A student cannot connect to another student's database | `connection … failed: User does not have CONNECT privilege` (PostgreSQL 16.3) |
| A student cannot connect to `postgres` / `template1` | refused **after** `00-harden.sql`; it succeeded before — the file is load-bearing |
| A student cannot create databases or roles | `permission denied to create database` / `… role` |
| Provisioning is idempotent and passwords are stable | second run: same `PGPASSWORD`, no errors |
| A student token works on its own collection | upsert, query, delete, count: HTTP 200 (Qdrant 1.20.0) |
| …and on nothing else | another student's collection: **403**; create a collection: **403**; drop own collection: **403**; collection list shows only their own |
| A short Qdrant key is refused | `provision_student.py` exits: the key signs the tokens and must be ≥ 32 bytes |
| Fuseki answers multi-hop queries | `cc:hasPrerequisite+` over 1,527 triples (Fuseki 6.2.0, Temurin 21) |
| Fuseki cannot be written to | update endpoint **404**; update body to the query endpoint **415**; `update=` form field **400**; graph-store write **404**; triple count unchanged |
| Fuseki has no UI and no admin API | `/`, `/$/datasets`, `/$/server`: **404** |
| `SERVICE` (server-side request forgery) is blocked | `SERVICE execution disabled` — HTTP 422 |
| Fuseki writes nothing to disk | its working directory was unchanged after a run → `readOnlyRootFilesystem` is safe |
| The Fuseki jar is the published one | sha1 matches Maven Central; the sha256 pinned in `fuseki/Dockerfile` was computed from that file |

**Not verified — needs a machine with Docker:** that `fuseki/Dockerfile` and
`docker-compose.yml` build and start (they are assembled from the pieces above,
which were each run, but the containers themselves were not).

## Deploying to a cluster later

`k8s/` and `kustomization.yaml` describe the three services in a namespace of
their own, `ai-data-services`, so they can be created and removed without
touching anything that exists. They were rendered with `kubectl kustomize`
(which contacts no cluster) and checked for internal consistency; they were
**not** validated against a live API server. When you decide to deploy:

```bash
kubectl kustomize platform/ | less                       # read what would be created
kubectl apply -k platform/ --dry-run=server              # let the API server validate it
cp platform/k8s/secrets.example.yaml platform/k8s/secrets.yaml   # fill in; gitignored
kubectl apply -f platform/k8s/secrets.yaml
kubectl apply -k platform/
```

Build and push the Fuseki image first and put its reference in
`k8s/30-fuseki.yaml`. Then provision students with the in-cluster addresses:

```
STUDENT_PGHOST=postgres.ai-data-services.svc.cluster.local
STUDENT_QDRANT_URL=http://qdrant.ai-data-services.svc.cluster.local:6333
STUDENT_FUSEKI_URL=http://fuseki.ai-data-services.svc.cluster.local:3030
STUDENT_GATEWAY_URL=http://bifrost-gateway.ai-lab.svc.cluster.local/v1
```

Things to settle before a real cohort (observed read-only on `platform-cluster`
on 2026-11-11; nothing was changed):

- **Network policy is not enforced.** The VPC CNI's policy agent runs with
  `--enable-network-policy=false`, so a `NetworkPolicy` object would be accepted
  and do nothing. That is why none is shipped here: isolation rests on the
  per-student credentials above, which were tested, not on network rules, which
  would be decoration. If you enable enforcement, restrict the three services to
  the namespaces student workspaces run in.
- **Capacity.** The Karpenter `default` NodePool is limited to 50 vCPU / 100 GiB.
  Fifty workspaces at 1 vCPU / 2 GiB each is exactly that, before these services
  and everything else on the cluster. Raise the limit or lower the per-workspace
  request before a class of fifty.
- **The gateway was scaled to zero** (`bifrost-gateway` 0/0) when this was
  written. It has to be running, and the virtual keys must allow a model that
  does tool calling, before `./check.sh env` can pass in a workspace.
- **Dedicated PostgreSQL.** Do not reuse `litellm-postgres`: `00-harden.sql`
  removes a default other applications may rely on, and every login can list
  role and database names on a shared server.
- **Scan the images** with Trivy after building, as for every image in this
  repo. An IDE scanner flagged the `eclipse-temurin:21-jre-alpine` base tag
  (1 critical, 2 high); `fuseki/Dockerfile` applies `apk upgrade`, which may or
  may not clear them — check the built image.

## Sizing

Tiny, by design. The policy corpus is 39 vectors per student; the graph is
1,527 triples; the dataset is 2,455 rows per student.

| Service | Request | Limit | Disk |
|---|---|---|---|
| PostgreSQL | 250m / 768Mi | 1 / 1.5Gi | 10Gi |
| Qdrant | 250m / 512Mi | 1 / 1Gi | 5Gi |
| Fuseki | 100m / 384Mi | 1 / 768Mi | none |

These are starting values, not measurements under load — no load test was run.
The number worth watching is PostgreSQL connections: each student role is
limited to 6, the server to 320.

## Checking a gateway key before giving it to a student

The agent needs a model that does **tool calling**, reached through the gateway,
with a key that is allowed to use it. `check_gateway.py` tests exactly that from
any machine with Python 3.8+ (no installs, no lab services needed):

```bash
python check_gateway.py --url https://ai-gateway.eks.dev.cream-collar.com --model claude-opus-5-5-bedrock
```

It asks for the key with a hidden prompt (or reads `GATEWAY_KEY` / `--key-file`)
and never prints it. For each model it runs a plain call and a two-step tool
call, and on LiteLLM it also shows the key's settings and its **owner's**:
LiteLLM refuses a key whose owner is set to "No Default Models" even when the
key's own list includes the model (`403 ... No default model access, only team
models allowed`). Every failure is printed with what it means and where to fix it.

## Files

```
platform/
├── README.md                 this file
├── check_gateway.py          can this key reach this model, and call tools? (run before handing out keys)
├── provision_student.py      create one student's database + collection, print their environment
├── provision-local.sh        the same, wired to the docker-compose stack
├── docker-compose.yml        postgres + qdrant + fuseki (+ the workspace, behind a profile)
├── env.example               secrets for the local stack -> copy to .env
├── postgres/00-harden.sql    one-time server hardening (mounted by compose AND the k8s ConfigMap)
├── fuseki/
│   ├── Dockerfile            Fuseki 6.2.0, plain server, checksum-pinned jar
│   ├── config.ttl            one read-only dataset, query timeout, SERVICE disabled
│   └── data/campus.ttl       the knowledge graph (GENERATED by tools/generate_dataset.py)
├── kustomization.yaml        renders k8s/ + the init ConfigMap   (NOT APPLIED)
└── k8s/                      namespace, postgres, qdrant, fuseki, secrets template   (NOT APPLIED)
```
