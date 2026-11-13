"""The platform self-test.  (PROVIDED)        ./check.sh env

These tests check the CONTAINER and the four services outside it - not your
code. They should all pass before you have written a line. If one fails, the
message says which service and what to tell your trainer.
"""

from __future__ import annotations

import importlib
import sys

import pytest

pytestmark = pytest.mark.environment

PACKAGES = ["strands", "openai", "psycopg", "sqlalchemy", "sqlglot", "qdrant_client", "fastembed",
            "rdflib", "httpx", "requests", "pandas", "numpy", "duckdb", "matplotlib", "plotly",
            "pydantic", "dotenv", "opentelemetry.sdk"]


def test_python_is_3_12():
    assert sys.version_info[:2] == (3, 12), f"expected Python 3.12, this is {sys.version.split()[0]}"


@pytest.mark.parametrize("module", PACKAGES)
def test_package_is_installed(module):
    try:
        importlib.import_module(module)
    except ImportError as exc:
        pytest.fail(f"`{module}` is missing from the image: {exc}. Tell your trainer - do not pip install it.",
                    pytrace=False)


def test_assignment_files_are_present(settings):
    missing = [str(p.relative_to(settings.root)) for p in (
        settings.data_dir / "student_performance.csv",
        settings.data_dir / "subject_details.csv",
        settings.data_dir / "department_details.csv",
        settings.schema_file,
        settings.root / "knowledge" / "graph" / "ONTOLOGY.md",
    ) if not p.is_file()]
    assert not missing, f"assignment files are missing: {missing}"
    policies = sorted(p.name for p in settings.policies_dir.glob("*.md"))
    assert len(policies) == 5, f"expected 5 policy documents, found {policies}"


def test_embedding_model_is_baked_into_the_image(settings):
    """No download, no network: the model must already be on disk."""
    from services.vector_client import embed

    vector = embed(["a short sentence"])[0]
    assert len(vector) == settings.embedding_dim, (
        f"the embedding model returned {len(vector)} dimensions, expected {settings.embedding_dim}")


def test_postgres_database_is_yours_to_write(postgres):
    from services.dataset_service import connect

    with connect() as conn:
        user, database = conn.execute("SELECT current_user, current_database()").fetchone()
        conn.execute("CREATE TABLE IF NOT EXISTS _environment_probe (x integer)")
        conn.execute("DROP TABLE _environment_probe")
    assert database not in ("postgres", "template1"), (
        f"you are connected to the maintenance database {database!r}, not your own - tell your trainer")
    assert user, "could not determine the database user"


def test_qdrant_collection_was_created_for_you(qdrant, settings):
    from services.vector_client import get_client

    client = get_client()
    name = settings.qdrant_collection
    assert client.collection_exists(name), (
        f"Qdrant collection {name!r} does not exist. It is created by the platform when your "
        "workspace is provisioned - tell your trainer.")
    size = client.get_collection(name).config.params.vectors.size
    assert size == settings.embedding_dim, (
        f"collection {name!r} stores {size}-dimensional vectors but the embedding model produces "
        f"{settings.embedding_dim} - tell your trainer.")


def test_knowledge_graph_holds_the_curriculum(fuseki, settings):
    import httpx

    query = ("PREFIX cc: <https://kg.cream-collar.com/campus/ontology#> "
             "SELECT (COUNT(?s) AS ?n) WHERE { ?s a cc:Subject }")
    response = httpx.post(settings.sparql_endpoint, data={"query": query},
                          headers={"Accept": "application/sparql-results+json"},
                          timeout=settings.http_timeout_s)
    response.raise_for_status()
    count = int(response.json()["results"]["bindings"][0]["n"]["value"])
    assert count == 100, f"the knowledge graph has {count} subjects, expected 100 - tell your trainer"


@pytest.mark.live
def test_gateway_accepts_your_key(gateway, settings):
    import httpx

    response = httpx.get(f"{settings.gateway_url}/models",
                         headers={"Authorization": f"Bearer {settings.api_key}"},
                         timeout=settings.http_timeout_s)
    assert response.status_code == 200, (
        f"the gateway answered HTTP {response.status_code} to your key: {response.text[:200]}")


@pytest.mark.live
def test_model_answers_a_plain_question(gateway, settings):
    from openai import OpenAI

    client = OpenAI(api_key=settings.api_key, base_url=settings.gateway_url, timeout=120)
    try:
        response = client.chat.completions.create(
            model=settings.model, max_tokens=512,
            messages=[{"role": "user", "content": "Reply with the single word: ready"}])
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"model {settings.model!r} could not be called through the gateway: "
                    f"{(str(exc).splitlines() or [''])[0][:300]}", pytrace=False)
    assert (response.choices[0].message.content or "").strip(), (
        f"model {settings.model!r} returned an empty reply")


@pytest.mark.live
def test_model_can_call_a_tool(gateway, settings):
    """The load-bearing assumption of the whole assignment.

    An agent is a model that asks for tools. If the configured model (or the
    gateway in front of it) does not support tool calling, nothing after
    Milestone 5 can work - and it is far better to learn that here than from a
    confusing failure in your own agent.
    """
    from strands import Agent, tool

    from services.llm_client import build_model

    calls = []

    @tool
    def add_numbers(a: int, b: int) -> dict:
        """Add two whole numbers and return their sum.

        Args:
            a: the first number.
            b: the second number.
        """
        calls.append((a, b))
        return {"sum": a + b}

    agent = Agent(model=build_model(), tools=[add_numbers], callback_handler=None,
                  system_prompt="You are a calculator. Always use the add_numbers tool to add.")
    try:
        result = agent("Use the add_numbers tool to add 17 and 25, then tell me the result.",
                       limits={"turns": 4})
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"a tool-calling request to {settings.model!r} failed: "
                    f"{(str(exc).splitlines() or [''])[0][:300]}\n"
                    "If plain chat works but this does not, the model does not support tool calling "
                    "through the gateway. Tell your trainer (LLM_MODEL / LLM_STREAM).", pytrace=False)
    assert calls, (f"model {settings.model!r} answered without calling the tool - it does not do "
                   "tool calling through this gateway. Tell your trainer.")
    assert sorted(calls[0]) == [17, 25], f"the tool was called with {calls[0]}, expected 17 and 25"
    assert "42" in str(result), f"the final answer does not contain 42: {str(result)[:200]!r}"
