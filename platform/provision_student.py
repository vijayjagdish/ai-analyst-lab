#!/usr/bin/env python3
"""Provision one student's private resources on the shared services.

For a student id this creates, idempotently:

    PostgreSQL   a login role and a database owned by it; nobody else may connect
    Qdrant       an empty collection, and a token that can read/write ONLY that
                 collection

and prints the environment block to hand to the student's workspace. Fuseki and
the Bifrost gateway need nothing per student here: the knowledge graph is one
shared read-only dataset, and gateway keys are minted by the existing tooling
(ai-lab/bifrost-gateway/mint-vk.sh or ai-key-api) and passed in with --ai-key.

    python provision_student.py --student stu-1001 --format env
    python provision_student.py --student stu-1001 --format json     # workspace API "environment"
    python provision_student.py --student stu-1001 --deprovision --yes

Admin connection details come from the environment so they never appear in a
shell history or a process list:

    PG_ADMIN_URL         postgresql://postgres:<pw>@<host>:5432/postgres
    QDRANT_ADMIN_URL     http://<host>:6333
    QDRANT_ADMIN_KEY     the Qdrant service.api_key (also signs student tokens)
    PROVISION_SECRET     any long random string; see "Passwords" below

and the addresses the STUDENT's container should use (in-cluster names usually
differ from the ones an admin laptop uses):

    STUDENT_PGHOST / STUDENT_PGPORT   default: host and port from PG_ADMIN_URL
    STUDENT_QDRANT_URL                default: QDRANT_ADMIN_URL
    STUDENT_FUSEKI_URL                e.g. http://fuseki.ai-data.svc.cluster.local:3030
    STUDENT_GATEWAY_URL               e.g. http://bifrost-gateway.ai-lab.svc.cluster.local/v1

Passwords
---------
The student's database password is HMAC-SHA256(PROVISION_SECRET, student id).
Nothing is stored: running this again for the same student yields the same
password, so a relaunched workspace gets working credentials without a secrets
table, and a leaked password reveals nothing about anyone else's. Rotating
PROVISION_SECRET rotates every password on the next run.

Needs: pip install "psycopg[binary]" pyjwt httpx   (all present in the lab image)
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

EMBEDDING_DIM = 384                 # BAAI/bge-small-en-v1.5, baked into the student image
TOKEN_TTL_DAYS = 45
STUDENT_CONNECTION_LIMIT = 6
STUDENT_STATEMENT_TIMEOUT = "30s"   # backstop; the agent's own SQL tool uses 5 s


def slug(student_id: str) -> str:
    """stu-1001 -> stu_1001. Only [a-z0-9_] ever reaches an identifier."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", student_id.strip().lower()).strip("_")
    if not cleaned:
        raise SystemExit(f"student id {student_id!r} has no usable characters")
    if not cleaned.startswith("stu"):
        cleaned = "stu_" + cleaned
    if len(cleaned) > 40:
        raise SystemExit(f"student id {student_id!r} is too long (40 characters after cleaning)")
    return cleaned


def derived_password(secret: str, name: str) -> str:
    digest = hmac.new(secret.encode(), f"pg:{name}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:32]


def need(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"set {name} (see the header of this script)")
    return value


# ── PostgreSQL ───────────────────────────────────────────────────────────────

def provision_postgres(admin_url: str, name: str, password: str) -> None:
    import psycopg
    from psycopg import sql

    ident = sql.Identifier(name)
    # CREATE DATABASE cannot run inside a transaction block.
    with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as conn:
        role_exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)).fetchone()
        verb = "ALTER" if role_exists else "CREATE"
        # A role is cluster-wide, so every attribute that matters is stated
        # explicitly rather than inherited from whatever the default is today.
        conn.execute(sql.SQL(
            "{} ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION "
            "CONNECTION LIMIT {} PASSWORD {}"
        ).format(sql.SQL(verb), ident, sql.Literal(STUDENT_CONNECTION_LIMIT), sql.Literal(password)))
        conn.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(
            ident, sql.Literal(STUDENT_STATEMENT_TIMEOUT)))
        conn.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '120s'").format(ident))

        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(ident, ident))
        # By default EVERY role may connect to a new database. Take that away;
        # the owner keeps access through ownership.
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(ident))


def deprovision_postgres(admin_url: str, name: str) -> None:
    import psycopg
    from psycopg import sql

    ident = sql.Identifier(name)
    with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(ident))
        conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(ident))


# ── Qdrant ───────────────────────────────────────────────────────────────────

def provision_qdrant(admin_url: str, admin_key: str, collection: str) -> str:
    import httpx
    import jwt

    headers = {"api-key": admin_key}
    with httpx.Client(base_url=admin_url.rstrip("/"), headers=headers, timeout=20) as client:
        exists = client.get(f"/collections/{collection}/exists")
        exists.raise_for_status()
        if not exists.json()["result"]["exists"]:
            created = client.put(f"/collections/{collection}", json={
                "vectors": {"size": EMBEDDING_DIM, "distance": "Cosine"},
                # Fifty tiny collections share one server. The default write-ahead
                # log is sized for millions of points; a policy corpus has ~40.
                "wal_config": {"wal_capacity_mb": 1},
            })
            created.raise_for_status()

    # Collection-scoped read/write. The student can upsert, delete and search
    # points in THIS collection and can neither see nor touch any other. They
    # cannot create or drop collections - which is why it is created above.
    #
    # ALWAYS include "access". A token signed with no access claim at all is a
    # full admin token.
    claims = {
        "access": [{"collection": collection, "access": "rw"}],
        "exp": int(time.time()) + TOKEN_TTL_DAYS * 86400,
    }
    return jwt.encode(claims, admin_key, algorithm="HS256")


def deprovision_qdrant(admin_url: str, admin_key: str, collection: str) -> None:
    import httpx

    response = httpx.delete(f"{admin_url.rstrip('/')}/collections/{collection}",
                            headers={"api-key": admin_key}, timeout=20)
    response.raise_for_status()


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Provision one student's database and vector collection.")
    parser.add_argument("--student", required=True, help="student id, e.g. stu-1001")
    parser.add_argument("--format", choices=("env", "json"), default="env",
                        help="env: KEY=VALUE lines; json: a list for the workspace API's `environment`")
    parser.add_argument("--ai-key", default=os.environ.get("STUDENT_AI_KEY", ""),
                        help="the student's Bifrost virtual key (sk-bf-...), minted separately")
    parser.add_argument("--model", default=os.environ.get("STUDENT_LLM_MODEL", ""),
                        help="override the image's default LLM_MODEL for this student")
    parser.add_argument("--deprovision", action="store_true",
                        help="DROP the student's database, role and collection")
    parser.add_argument("--yes", action="store_true", help="required with --deprovision")
    args = parser.parse_args()

    name = slug(args.student)
    collection = f"{name}_policies"
    pg_admin = need("PG_ADMIN_URL")
    qdrant_admin_url = need("QDRANT_ADMIN_URL")
    qdrant_admin_key = need("QDRANT_ADMIN_KEY")
    # The Qdrant API key is also the HS256 secret that signs every student
    # token. A short key is a short signing secret: anyone holding one token can
    # brute-force it offline and then mint an admin token.
    if len(qdrant_admin_key.encode()) < 32:
        raise SystemExit("QDRANT_ADMIN_KEY must be at least 32 bytes - it signs the student tokens. "
                         "Generate one with: openssl rand -base64 48")

    if args.deprovision:
        if not args.yes:
            raise SystemExit(f"--deprovision deletes database {name!r} and collection {collection!r}; "
                             "add --yes to confirm")
        deprovision_postgres(pg_admin, name)
        deprovision_qdrant(qdrant_admin_url, qdrant_admin_key, collection)
        print(f"removed database/role {name} and collection {collection}", file=sys.stderr)
        return 0

    password = derived_password(need("PROVISION_SECRET"), name)
    provision_postgres(pg_admin, name, password)
    token = provision_qdrant(qdrant_admin_url, qdrant_admin_key, collection)

    admin = urlparse(pg_admin)
    env = {
        "STUDENT_ID": args.student,
        "PGHOST": os.environ.get("STUDENT_PGHOST", admin.hostname or "localhost"),
        "PGPORT": os.environ.get("STUDENT_PGPORT", str(admin.port or 5432)),
        "PGDATABASE": name,
        "PGUSER": name,
        "PGPASSWORD": password,
        "QDRANT_URL": os.environ.get("STUDENT_QDRANT_URL", qdrant_admin_url),
        "QDRANT_API_KEY": token,
        "QDRANT_COLLECTION": collection,
    }
    for key, source in (("FUSEKI_URL", "STUDENT_FUSEKI_URL"), ("GATEWAY_URL", "STUDENT_GATEWAY_URL")):
        if os.environ.get(source):
            env[key] = os.environ[source]
    if args.ai_key:
        env["AI_KEY"] = args.ai_key
    if args.model:
        env["LLM_MODEL"] = args.model

    if args.format == "json":
        print(json.dumps([f"{key}={value}" for key, value in env.items()], indent=2))
    else:
        for key, value in env.items():
            print(f"{key}={value}")
    print(f"provisioned {args.student}: database {name}, collection {collection} "
          f"(token valid {TOKEN_TTL_DAYS} days)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
