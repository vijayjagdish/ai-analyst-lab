"""Every setting the assignment reads, in one place.  (PROVIDED - nothing to do here.)

Four services live OUTSIDE your container. This module is the only code that
knows where they are; everything else calls get_settings().

    Bifrost gateway    OPENAI_BASE_URL, OPENAI_API_KEY, LLM_MODEL
    PostgreSQL         PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD   (or DATABASE_URL)
    Qdrant             QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION
    Apache Jena Fuseki FUSEKI_URL, FUSEKI_DATASET                    (or SPARQL_ENDPOINT)

Where the values come from
--------------------------
1. The platform injects them into the container's environment at launch.
2. The file `.env` in this assignment folder is read on top of that, and WINS.
   That is deliberate: edit `.env`, re-run your cell, and the new value is used.
   No container restart.

The PostgreSQL settings use the standard libpq variable names on purpose. That
is why `psql` in a terminal connects to your database with no arguments at all.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    """A required setting is missing. The message says which one and where to set it."""


def _load_env_file() -> None:
    """Read .env over the process environment (skipped when ANALYST_ENV_FILE is empty)."""
    target = os.environ.get("ANALYST_ENV_FILE")
    if target == "":
        return                      # explicit opt-out, used by the grader
    path = Path(target) if target else ROOT / ".env"
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:             # the image always has it; be kind elsewhere
        return
    load_dotenv(path, override=True)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}") from exc


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    root: Path

    # ── LLM, through the Bifrost gateway (OpenAI-compatible) ─────────────────
    gateway_url: str
    api_key: str
    model: str
    max_tokens: int
    stream: bool
    extra_params: dict = field(default_factory=dict)

    # ── PostgreSQL: YOUR OWN database ────────────────────────────────────────
    # Empty means "let libpq read PGHOST/PGDATABASE/... from the environment".
    database_url: str = ""

    # ── Qdrant: YOUR OWN collection ──────────────────────────────────────────
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = ""
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    # ── Apache Jena Fuseki: the SHARED, read-only knowledge graph ────────────
    sparql_endpoint: str = ""

    # ── Guard rails ──────────────────────────────────────────────────────────
    sql_max_rows: int = 200
    sql_timeout_ms: int = 5000
    agent_max_turns: int = 12
    http_timeout_s: int = 20

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def policies_dir(self) -> Path:
        return self.root / "knowledge" / "policies"

    @property
    def schema_file(self) -> Path:
        return self.root / "sql" / "schema.sql"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def charts_dir(self) -> Path:
        return self.output_dir / "charts"

    def require(self, *names: str) -> None:
        """Raise a readable error if any of the named settings is empty."""
        hints = {
            "api_key": "OPENAI_API_KEY (your gateway key, sk-bf-...) - put it in .env",
            "gateway_url": "OPENAI_BASE_URL (the Bifrost /v1 address)",
            "qdrant_url": "QDRANT_URL",
            "qdrant_collection": "QDRANT_COLLECTION (the collection created for you)",
            "sparql_endpoint": "FUSEKI_URL (or SPARQL_ENDPOINT)",
        }
        missing = [hints.get(name, name) for name in names if not getattr(self, name)]
        if missing:
            raise ConfigError(
                "Missing setting(s): " + "; ".join(missing)
                + ". Run `python -m agent.main --doctor` to see what is configured."
            )


_cached: Settings | None = None


def load_settings() -> Settings:
    _load_env_file()

    endpoint = os.environ.get("SPARQL_ENDPOINT", "").strip()
    if not endpoint:
        base = os.environ.get("FUSEKI_URL", "").strip().rstrip("/")
        dataset = os.environ.get("FUSEKI_DATASET", "campus").strip().strip("/")
        endpoint = f"{base}/{dataset}/sparql" if base else ""

    extra_raw = os.environ.get("LLM_EXTRA_PARAMS", "").strip()
    try:
        extra = json.loads(extra_raw) if extra_raw else {}
    except json.JSONDecodeError as exc:
        raise ConfigError(f"LLM_EXTRA_PARAMS is not valid JSON: {exc}") from exc
    if not isinstance(extra, dict):
        raise ConfigError("LLM_EXTRA_PARAMS must be a JSON object, e.g. {\"reasoning_effort\": \"low\"}")

    return Settings(
        root=ROOT,
        gateway_url=os.environ.get("OPENAI_BASE_URL", "").strip().rstrip("/"),
        api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
        model=os.environ.get("LLM_MODEL", "anthropic/claude-opus-5-5").strip(),
        max_tokens=_int("LLM_MAX_TOKENS", 16000),
        stream=_bool("LLM_STREAM", True),
        extra_params=extra,
        database_url=os.environ.get("DATABASE_URL", "").strip(),
        qdrant_url=os.environ.get("QDRANT_URL", "").strip(),
        qdrant_api_key=os.environ.get("QDRANT_API_KEY", "").strip(),
        qdrant_collection=os.environ.get("QDRANT_COLLECTION", "").strip(),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5").strip(),
        embedding_dim=_int("EMBEDDING_DIM", 384),
        sparql_endpoint=endpoint,
        sql_max_rows=_int("SQL_MAX_ROWS", 200),
        sql_timeout_ms=_int("SQL_TIMEOUT_MS", 5000),
        agent_max_turns=_int("AGENT_MAX_TURNS", 12),
        http_timeout_s=_int("HTTP_TIMEOUT_S", 20),
    )


def get_settings(reload: bool = False) -> Settings:
    """The settings, read once. Pass reload=True after editing .env in a live kernel."""
    global _cached
    if _cached is None or reload:
        _cached = load_settings()
    return _cached


def describe() -> dict:
    """What is configured, with secrets masked. Safe to print or paste into a ticket."""
    s = get_settings(reload=True)

    def mask(secret: str) -> str:
        if not secret:
            return "(not set)"
        return secret[:6] + "..." + secret[-4:] if len(secret) > 14 else "(set)"

    return {
        "gateway_url": s.gateway_url or "(not set)",
        "api_key": mask(s.api_key),
        "model": s.model,
        "postgres": s.database_url.split("@")[-1] if s.database_url else (
            f"{os.environ.get('PGUSER', '?')}@{os.environ.get('PGHOST', '?')}:"
            f"{os.environ.get('PGPORT', '5432')}/{os.environ.get('PGDATABASE', '?')}"),
        "qdrant_url": s.qdrant_url or "(not set)",
        "qdrant_api_key": mask(s.qdrant_api_key),
        "qdrant_collection": s.qdrant_collection or "(not set)",
        "sparql_endpoint": s.sparql_endpoint or "(not set)",
        "embedding_model": s.embedding_model,
    }
