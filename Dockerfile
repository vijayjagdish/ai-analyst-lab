# =============================================================================
# AI Analyst Lab — JupyterLab + Strands Agents SDK
# CreamCollar LXP · "Build a Grounded AI Data Analyst Agent"
#
# This image is the STUDENT'S WORKSPACE and nothing else. The four services the
# agent talks to run OUTSIDE it and are shared by the class:
#
#     Bifrost gateway (LLM)   PostgreSQL   Qdrant   Apache Jena Fuseki
#
# so there is no database, no vector store and no JVM in here — which is why
# this is a ~1.5 GB image and not a 6 GB one, and why fifty students do not
# each run their own copy of everything.
#
# Same operator contract as llm-lab / sdv-ml-lab / ai-lab: UID 1000 `student`,
# seed-once workspace guarded by a marker file, WORKSPACE_MOUNT_PATH honoured,
# iframe-safe Jupyter flags, ENTRYPOINT (not CMD).
#
# The trainer's materials (reference solution, hidden tests, grade.py) are NOT
# in this image. They are a second, thin image built on top of this one — see
# trainer/Dockerfile — so a student's container cannot contain the answers.
#
# UNBUILT: this was written on a workstation with no docker CLI. Everything
# that could be checked without a build was (see README.md, "What was verified").
#     docker build -t ai-analyst-lab:v1 .
# =============================================================================

FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# =============================================================================
# STAGE 1: System dependencies — minimal
#   - git   : students version their work
#   - gosu  : entrypoint runs as root to chown the EFS mount, then drops to
#             UID 1000 before launching Jupyter
#   - nano  : students edit .env from a terminal; the slim base ships no editor
#   - curl  : knowledge/graph/ONTOLOGY.md teaches the SPARQL protocol with a
#             curl example, and it fetches the PostgreSQL signing key below
#   - postgresql-client-16 : `psql` with no arguments lands in the student's
#             own database (the PG* variables are injected).
#
# Why the client comes from apt.postgresql.org and not from Debian: bookworm
# ships psql 15, and psql 15 talking to a version 16 server prints
#     WARNING: psql major version 15, server major version 16.
#              Some psql features might not work.
# on every start. Harmless, and exactly the kind of line that makes a student
# think their database is broken. The lab's server is PostgreSQL 16
# (platform/docker-compose.yml); keep the two major versions in step.
# Checked 2026-11-12: bookworm-pgdg is served and carries postgresql-client-16.
#
#   - No build-essential: every wheel below is prebuilt for cp312/manylinux.
# =============================================================================
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        git \
        nano \
        ca-certificates \
        gosu \
        curl \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
         https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
         > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# =============================================================================
# STAGE 2: JupyterLab + the agent stack
#
# requirements.txt pins the direct dependencies; constraints.txt pins all 166
# packages they resolve to, for linux/x86_64 + Python 3.12, wheels only. With
# both, two builds a month apart install the same bytes. That matters here more
# than usual: the checkpoint tests assert which policy rule an embedding
# retrieves and how sqlglot parses a statement, so a silently newer release
# could turn a correct submission red.
# =============================================================================
COPY requirements.txt constraints.txt /tmp/build/
RUN pip install --upgrade pip \
    && pip install -r /tmp/build/requirements.txt -c /tmp/build/constraints.txt \
    && python -m ipykernel install --sys-prefix --name python3 --display-name "Python 3 (Analyst Agent Lab)" \
    && rm -rf /tmp/build

# =============================================================================
# STAGE 3: Bake the embedding model
#
# BAAI/bge-small-en-v1.5 (ONNX, ~67 MB, 384 dimensions) is downloaded ONCE, at
# build time, into a fixed cache directory. At runtime:
#   - no student container needs egress to huggingface.co
#   - the first search does not stall on a download
#   - every student embeds with the same weights, which is what lets a test say
#     "this question must retrieve rule AR-2"
# HF_HUB_OFFLINE=1 then turns any attempt to fetch a model into an immediate
# error instead of a hang. The python -c line embeds one sentence and checks
# the dimension, so a broken download fails the BUILD, not a student's
# Milestone 4.
#
# The cache is handed to UID 1000 (the `student` user, created below) because
# the model loader runs as that user and the Hugging Face cache layer may want
# to create a lock file beside the model. /opt is not on the persistent
# volume, so a student who damages it gets a clean copy on the next restart.
# =============================================================================
ENV FASTEMBED_CACHE_PATH=/opt/fastembed_cache
RUN python -c "from fastembed import TextEmbedding; m = TextEmbedding('BAAI/bge-small-en-v1.5'); v = list(m.embed(['build check']))[0]; assert len(v) == 384, len(v)" \
    && chown -R 1000:1000 /opt/fastembed_cache \
    && chmod -R a+rX /opt/fastembed_cache
ENV HF_HUB_OFFLINE=1

# =============================================================================
# STAGE 4: student user (non-root, UID 1000)
# Same name and UID as every other lab image in this repo, so the platform's
# EFS access points and fsGroup settings apply unchanged.
# =============================================================================
RUN groupadd -g 1000 workspace \
    && useradd -m -u 1000 -g workspace -s /bin/bash student

# =============================================================================
# STAGE 5: Content, kept OUT of the persistent mount
#
# /opt/assignment-default is the pristine starter. entrypoint.sh seeds it into
# the workspace ONCE, guarded by a marker file on the persistent volume, so a
# student who edits a file does not get it silently restored on restart.
#
# home-default/ is GENERATED from assignment-src/ by tools/build_assignment.py
# (the reference solution with the solutions stripped). Only home-default/ is
# copied here: the solution never enters this image.
# =============================================================================
RUN mkdir -p /opt/assignment-default
COPY --chown=student:workspace home-default/ /opt/assignment-default/
COPY scripts/entrypoint.sh /entrypoint.sh

# CRLF in a shebang line makes the kernel report "no such file or directory"
# for the interpreter, which is an unhelpful way to find out the repo was
# cloned on Windows.
RUN find /opt/assignment-default -name '*.sh' -exec sed -i 's/\r$//' {} \; \
    && find /opt/assignment-default -name '*.sh' -exec chmod +x {} \; \
    && sed -i 's/\r$//' /entrypoint.sh \
    && chmod +x /entrypoint.sh

# =============================================================================
# STAGE 6: Runtime
# =============================================================================
# Entrypoint starts as root so it can chown a host-mounted or EFS-backed
# workspace, then drops to UID 1000 via gosu before launching Jupyter.
USER root
WORKDIR /home/student

ENV ROLE=student
ENV JUPYTER_PORT=8888
ENV HOME=/home/student
# No __pycache__ folders in the workspace: they are clutter in a submission.
ENV PYTHONDONTWRITEBYTECODE=1

# Default model, as the Bifrost gateway names it (<provider>/<model>). Override
# per workspace with "LLM_MODEL=..." in the provisioning `environment` list.
# The agent needs a model that does TOOL CALLING; `gemma` on Bedrock does not.
ENV LLM_MODEL=anthropic/claude-opus-5-5

# Gateway endpoint: the cluster-internal service name, which resolves only from
# pods inside the cluster. A platform-injected GATEWAY_URL wins over this.
ENV GATEWAY_URL=http://bifrost-gateway.ai-lab.svc.cluster.local/v1

# Everything else is PER STUDENT and injected at provisioning — the output of
# platform/provision_student.py is exactly this list:
#     AI_KEY
#     PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD
#     QDRANT_URL QDRANT_API_KEY QDRANT_COLLECTION
#     FUSEKI_URL
# None of them is defaulted here on purpose: a baked value would be the wrong
# student's database, and a wrong default that half-works is worse than a clear
# "not set" from `python -m agent.main --doctor`.

VOLUME ["/home/student"]

EXPOSE 8888

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8888/api',timeout=5).status==200 else 1)" || exit 1

# ENTRYPOINT, *not* CMD. Load-bearing on the platform: the workspace-operator
# injects a default `args` list built for its original openvscode-server image
# when spec.args is unset. Kubernetes `args` REPLACES the image's CMD but is
# APPENDED to its ENTRYPOINT — with CMD the container command becomes those
# flags alone and the pod crash-loops on
#     exec: "--host": executable file not found in $PATH
# As an ENTRYPOINT the script always runs and the flags arrive as "$@", ignored.
ENTRYPOINT ["/entrypoint.sh"]
