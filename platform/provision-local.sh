#!/usr/bin/env bash
# Provision one student on the LOCAL docker-compose stack and write their
# environment file.
#
#     bash provision-local.sh stu-1001                  # -> student.env (the compose `workspace` service)
#     bash provision-local.sh stu-1002 stu-1002.env     # -> stu-1002.env (for `docker run --env-file`)
#
# Run it on the machine running `docker compose up`, after the three services
# are healthy. It talks to them on localhost (the published ports) and writes
# the IN-NETWORK names (postgres, qdrant, fuseki) into student.env, because
# that is what the workspace container must use.
#
# Needs Python 3 with three packages. On Ubuntu, in a virtual environment:
#     sudo apt-get install -y python3-venv
#     python3 -m venv ~/lab-venv
#     ~/lab-venv/bin/pip install "psycopg[binary]" pyjwt httpx
#     source ~/lab-venv/bin/activate
# (Set PYTHON=/path/to/python to use a specific interpreter.)
set -euo pipefail
cd "$(dirname "$0")"

STUDENT="${1:?usage: provision-local.sh <student-id> [output-file]}"
OUT="${2:-student.env}"
[ -f .env ] || { echo "copy env.example to .env and fill it in first" >&2; exit 1; }
set -a; . ./.env; set +a

: "${PG_ADMIN_PASSWORD:?set PG_ADMIN_PASSWORD in .env}"
: "${QDRANT_ADMIN_KEY:?set QDRANT_ADMIN_KEY in .env}"
: "${PROVISION_SECRET:?set PROVISION_SECRET in .env}"

PYTHON="${PYTHON:-python3}"
if ! "${PYTHON}" -c "import psycopg, jwt, httpx" 2>/dev/null; then
    echo "${PYTHON} cannot import psycopg, jwt and httpx - see the header of this script" >&2
    exit 1
fi

# The ports published by docker-compose.yml (same variables, same defaults).
export PG_ADMIN_URL="postgresql://postgres:${PG_ADMIN_PASSWORD}@127.0.0.1:${PG_LOCAL_PORT:-5432}/postgres"
export QDRANT_ADMIN_URL="http://127.0.0.1:${QDRANT_LOCAL_PORT:-6333}"
export QDRANT_ADMIN_KEY PROVISION_SECRET

# What the STUDENT's container uses: compose service names and the ports
# INSIDE the compose network, which never change.
export STUDENT_PGHOST=postgres STUDENT_PGPORT=5432
export STUDENT_QDRANT_URL="http://qdrant:6333"
export STUDENT_FUSEKI_URL="http://fuseki:3030"
[ -n "${GATEWAY_URL:-}" ] && export STUDENT_GATEWAY_URL="${GATEWAY_URL}"
[ -n "${AI_KEY:-}" ] && export STUDENT_AI_KEY="${AI_KEY}"
# STUDENT_LLM_MODEL, if set in .env, is picked up by provision_student.py itself.

# Write to a temporary file first: a failed run must not leave a half-written
# environment file behind for the workspace to start with.
"${PYTHON}" provision_student.py --student "${STUDENT}" --format env > "${OUT}.tmp"
mv "${OUT}.tmp" "${OUT}"
chmod 600 "${OUT}"
echo "wrote ${OUT} for ${STUDENT}"
if [ "${OUT}" = "student.env" ]; then
    echo "start the workspace with:  docker compose --profile workspace up -d"
    echo "then open http://localhost:${WORKSPACE_LOCAL_PORT:-8888}/lab"
else
    echo "start the workspace with, for example:"
    echo "  docker run -d --name ws-${STUDENT} --network platform_default --env-file ${OUT} \\"
    echo "    -p 127.0.0.1:8889:8888 -v ws-${STUDENT}:/home/student ai-analyst-lab:v1"
fi
