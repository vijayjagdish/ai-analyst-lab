#!/bin/bash
set -e

JUPYTER_PORT=${JUPYTER_PORT:-8888}
RUN_AS_USER=student
RUN_AS_UID=1000
RUN_AS_GID=1000

ASSIGNMENT_DEFAULT=/opt/assignment-default
TRAINER_DEFAULT=/opt/trainer-default          # exists only in the trainer image
ASSIGNMENT_NAME=analyst-agent-assignment

# student | trainer. Anything else is treated as student, because a typo in a
# provisioning request must not be the thing that hands out the answer key.
ROLE="${ROLE:-student}"
case "${ROLE}" in
    student|trainer) ;;
    *)  echo "[init] WARNING: unknown ROLE='${ROLE}' - falling back to 'student'"
        ROLE=student ;;
esac
if [ "${ROLE}" = "trainer" ] && [ ! -d "${TRAINER_DEFAULT}" ]; then
    # The trainer materials are a separate image (trainer/Dockerfile). Asking
    # for ROLE=trainer on the student image cannot produce them.
    echo "[init] WARNING: ROLE=trainer but this is the student image (no ${TRAINER_DEFAULT}) - running as student"
    ROLE=student
fi

# Where the persistent volume is mounted. The Workspace CRD's spec.mountPath is
# passed in as an env var by the operator - the image cannot know it at build
# time. Same lookup chain as llm-lab / sdv-ml-lab so all images behave alike.
# Deliberately NOT baked as an ENV in the Dockerfile: a baked value would always
# win this lookup and mask whatever the platform actually injected.
WORKSPACE_DIR="${WORKSPACE_MOUNT_PATH:-${MOUNT_PATH:-/home/student}}"
case "${WORKSPACE_DIR}" in
    /*) ;;
    *)  echo "[init] WARNING: WORKSPACE_DIR='${WORKSPACE_DIR}' is not absolute - using /home/student"
        WORKSPACE_DIR=/home/student ;;
esac
export WORKSPACE_DIR
ASSIGNMENT_DIR="${WORKSPACE_DIR}/${ASSIGNMENT_NAME}"

# ── Model gateway wiring ─────────────────────────────────────────────────────
# The platform speaks AI_KEY / GATEWAY_URL (as it does for every lab in this
# repo); the assignment's code reads the OpenAI-standard names. Translate here.
#
# The KEY also goes into the workspace .env (created below, once) so a student
# can replace it without a container restart. The URL is exported into the
# process environment only and never written to a file the student edits.
#
# No real provider credential exists anywhere in this container - the gateway
# holds those. The same is true of the other three services: the student holds
# a database password for ONE database and a token for ONE vector collection.
AI_KEY="${AI_KEY:-${OPENAI_API_KEY:-}}"
GATEWAY_URL="${GATEWAY_URL:-${OPENAI_BASE_URL:-}}"
LLM_MODEL="${LLM_MODEL:-anthropic/claude-opus-5-5}"
export LLM_MODEL
[ -n "${GATEWAY_URL}" ] && export OPENAI_BASE_URL="${GATEWAY_URL}"
# Exported only when provided - an empty value here would shadow the .env.
[ -n "${AI_KEY}" ] && export OPENAI_API_KEY="${AI_KEY}"

echo "============================================"
echo "  AI Analyst Lab - JupyterLab starting"
echo "  Role       : ${ROLE}"
echo "  Gateway    : ${GATEWAY_URL:-(not set)}"
echo "  Model      : ${LLM_MODEL}"
echo "  PostgreSQL : ${PGUSER:-(not set)}@${PGHOST:-(not set)}:${PGPORT:-5432}/${PGDATABASE:-(not set)}"
echo "  Qdrant     : ${QDRANT_URL:-(not set)}  collection=${QDRANT_COLLECTION:-(not set)}"
echo "  Fuseki     : ${FUSEKI_URL:-(not set)}"
echo "  Workspace  : ${WORKSPACE_DIR}  (the only path that persists)"
echo "  Browser    : http://localhost:${JUPYTER_PORT}/lab"
echo "============================================"

# Say WHICH injected value is missing, at start-up, in the pod log - the place
# an operator looks first. The student-facing equivalent is
# `python -m agent.main --doctor`.
MISSING=""
[ -z "${AI_KEY}" ]            && MISSING="${MISSING} AI_KEY"
[ -z "${PGHOST}" ]            && MISSING="${MISSING} PGHOST"
[ -z "${PGDATABASE}" ]        && MISSING="${MISSING} PGDATABASE"
[ -z "${PGPASSWORD}" ]        && MISSING="${MISSING} PGPASSWORD"
[ -z "${QDRANT_URL}" ]        && MISSING="${MISSING} QDRANT_URL"
[ -z "${QDRANT_COLLECTION}" ] && MISSING="${MISSING} QDRANT_COLLECTION"
[ -z "${FUSEKI_URL}" ]        && MISSING="${MISSING} FUSEKI_URL"
if [ -n "${MISSING}" ]; then
    echo "[init] WARNING: not injected:${MISSING}"
    echo "[init]          the workspace will start, but those services will be unreachable."
    echo "[init]          Provision with platform/provision_student.py and pass its output as environment."
fi

mkdir -p "${WORKSPACE_DIR}"

# EFS access points enforce their own ownership, so an unguarded chown exits
# non-zero and kills the pod under `set -e`. Best-effort only - on EKS the Pod
# spec's fsGroup is what actually makes the mount writable.
chown "${RUN_AS_UID}:${RUN_AS_GID}" "${WORKSPACE_DIR}" 2>/dev/null || true
chown -R "${RUN_AS_UID}:${RUN_AS_GID}" "/home/${RUN_AS_USER}" 2>/dev/null || true

# ── Seed content, ONCE ───────────────────────────────────────────────────────
# The marker lives on the persistent volume. A student who edits or deletes a
# file does not get it silently restored on the next start - their work is the
# artifact being assessed, and re-seeding over it would destroy submissions.
seed_once() {   # seed_once SOURCE_DIR TARGET_DIR MARKER_NAME LABEL
    local src="$1" dst="$2" marker="${WORKSPACE_DIR}/$3" label="$4"
    if [ -f "${marker}" ]; then
        echo "[init] ${label} already seeded (${marker} exists) - leaving it alone"
        return 0
    fi
    echo "[init] seeding ${label} into ${dst}"
    mkdir -p "${dst}"
    # -n: never clobber a file that is already there, even if the marker is
    # missing (e.g. someone deleted it by hand).
    cp -rn "${src}/." "${dst}/" 2>/dev/null || true
    chown -R "${RUN_AS_UID}:${RUN_AS_GID}" "${dst}" 2>/dev/null || true
    touch "${marker}" 2>/dev/null || true
}

seed_once "${ASSIGNMENT_DEFAULT}" "${WORKSPACE_DIR}" .assignment-seeded "assignment"
if [ "${ROLE}" = "trainer" ]; then
    # A trainer gets the student's view AND the reference solution, the hidden
    # tests and the answer key, so they can demo the assignment and grade
    # against the same rubric.
    seed_once "${TRAINER_DEFAULT}" "${WORKSPACE_DIR}/trainer-only" .trainer-seeded "trainer materials"
fi

# ── Workspace .env - the file the student actually edits ─────────────────────
# Created ONCE (it lives on the persistent volume). Holds the gateway KEY and
# the model only. Never overwritten on restart: a student who pasted a
# replacement key keeps it.
ENV_FILE="${ASSIGNMENT_DIR}/.env"
if [ -d "${ASSIGNMENT_DIR}" ] && [ ! -f "${ENV_FILE}" ]; then
    echo "[init] creating ${ENV_FILE}"
    cat > "${ENV_FILE}" <<ENV
# Your gateway key and model. Edit, save, re-run - no restart needed.
# NEVER commit or share this file. See .env.template for every other setting.

# Your personal gateway key (starts with sk-bf-)
OPENAI_API_KEY=${AI_KEY}

# Model, as the gateway names it (do not change unless instructed)
LLM_MODEL=${LLM_MODEL}
ENV
    chown "${RUN_AS_UID}:${RUN_AS_GID}" "${ENV_FILE}" 2>/dev/null || true
    chmod 600 "${ENV_FILE}" 2>/dev/null || true
fi

# ── Terminal environment ─────────────────────────────────────────────────────
# New terminals open in the assignment folder, where ./check.sh and
# `python -m agent.main` are run from. The PG* variables are already in the
# environment, which is why a bare `psql` connects to the student's database.
if ! grep -q "${ASSIGNMENT_NAME}" "/home/${RUN_AS_USER}/.bashrc" 2>/dev/null; then
    cat >> "/home/${RUN_AS_USER}/.bashrc" <<BASHRC
export WORKSPACE_DIR="${WORKSPACE_DIR}"
cd "${ASSIGNMENT_DIR}" 2>/dev/null || cd "\$WORKSPACE_DIR" 2>/dev/null || true
BASHRC
    chown "${RUN_AS_UID}:${RUN_AS_GID}" "/home/${RUN_AS_USER}/.bashrc" 2>/dev/null || true
fi

# git needs an identity before `git commit` works, and "please tell me who you
# are" mid-assignment is a support ticket, not a learning moment.
GIT_CFG="/home/${RUN_AS_USER}/.gitconfig"
if [ ! -f "${GIT_CFG}" ]; then
    cat > "${GIT_CFG}" <<GITEOF
[user]
    name = ${GIT_USER_NAME:-Analyst Lab Student}
    email = ${GIT_USER_EMAIL:-student@creamcollar.local}
[init]
    defaultBranch = main
[safe]
    directory = *
GITEOF
    chown "${RUN_AS_UID}:${RUN_AS_GID}" "${GIT_CFG}" 2>/dev/null || true
fi

cd "${WORKSPACE_DIR}"

echo ""
echo "============================================"
echo "  READY  ·  role=${ROLE}"
echo "  Open: http://YOUR_IP:${JUPYTER_PORT}/lab"
echo "  Work saved to: ${WORKSPACE_DIR} (nothing else persists)"
echo "============================================"

# Drop privileges to UID 1000 and exec JupyterLab as the foreground process.
#   - No token / password: the platform fronts this with an authenticating
#     proxy, matching every other image in this repo.
#   - disable_check_xsrf + allow_origin: Jupyter runs inside a cross-origin
#     iframe on the student platform. Without these, every POST (kernel start,
#     file save) fails with "_xsrf argument missing from POST".
#   - root_dir=WORKSPACE_DIR: the file browser opens on the persistent volume,
#     so a student cannot save work somewhere that vanishes.
#   - allow_hidden: the student edits the assignment's .env from the file
#     browser (View -> Show Hidden Files).
# gosu keeps the environment, so kernels and terminals inherit the injected
# PG*, QDRANT_*, FUSEKI_URL and OPENAI_* variables.
exec gosu "${RUN_AS_USER}" env \
    HOME="/home/${RUN_AS_USER}" \
    SHELL="/bin/bash" \
    ROLE="${ROLE}" \
    WORKSPACE_DIR="${WORKSPACE_DIR}" \
    JUPYTER_PORT="${JUPYTER_PORT}" \
    jupyter lab \
        --ip=0.0.0.0 \
        --port="${JUPYTER_PORT}" \
        --no-browser \
        --ServerApp.token='' \
        --ServerApp.password='' \
        --ServerApp.disable_check_xsrf=True \
        --ServerApp.allow_origin='*' \
        --ServerApp.allow_remote_access=True \
        --ServerApp.root_dir="${WORKSPACE_DIR}" \
        --ContentsManager.allow_hidden=True \
        --ServerApp.terminado_settings="shell_command=['/bin/bash']"
