"""Shared pytest fixtures for the checkpoint tests.  (PROVIDED)

    ./check.sh env     the container and the four services - green from day one
    ./check.sh 3       milestone 3's checkpoint
    ./check.sh all     every milestone, summarised

Milestone tests are RED until you do the milestone. That is the design: a
checkpoint that passes before you write anything is not a checkpoint.

`tests/test_environment.py` is the exception. It tests the PLATFORM, not your
code. If it is red, stop and tell your trainer - nothing you write will work
until it is green.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: calls the language model through the gateway (costs budget)")
    config.addinivalue_line("markers", "environment: checks the platform, not your code")


def _todo_message(exc: BaseException) -> str:
    return f"Not implemented yet: {exc}. Open the file, find that TODO and complete it."


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item):
    """Turn a TODO that has not been done yet into one readable line instead of a traceback."""
    try:
        return (yield)
    except NotImplementedError as exc:
        pytest.fail(_todo_message(exc), pytrace=False)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item):
    """The same, when the unfinished TODO is reached through a fixture.

    Several fixtures call YOUR code (loaded_data runs your load_dataset()). An
    exception inside a fixture is normally reported as an ERROR with a long
    traceback, which reads as "the test suite is broken". It is not - a
    milestone is simply not done - so the test is made to FAIL with the same
    one-line message instead.
    """
    try:
        return (yield)
    except NotImplementedError as exc:
        message = _todo_message(exc)

        def fail_instead() -> None:
            pytest.fail(message, pytrace=False)

        item.runtest = fail_instead
        return None


def _first_line(exc: BaseException) -> str:
    return (str(exc).strip().splitlines() or [type(exc).__name__])[0][:200]


@pytest.fixture(scope="session")
def settings():
    from services.config import get_settings
    return get_settings(reload=True)


@pytest.fixture(scope="session")
def expected() -> dict:
    """Figures computed from the data ahead of time (tests/expected.json)."""
    return json.loads((Path(__file__).parent / "expected.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def postgres(settings):
    """Fails - with the reason - if your PostgreSQL database cannot be reached."""
    from services.dataset_service import connect
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"PostgreSQL is not reachable: {_first_line(exc)}\n"
                    "Run `python -m agent.main --doctor`. This is a platform problem, not your code.",
                    pytrace=False)
    return True


@pytest.fixture(scope="session")
def loaded_data(postgres):
    """The dataset, loaded once per test session by YOUR load_dataset()."""
    from services.dataset_service import load_dataset
    return load_dataset()


@pytest.fixture(scope="session")
def qdrant(settings):
    from services.vector_client import get_client
    try:
        get_client().collection_exists(settings.qdrant_collection)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"Qdrant is not reachable: {_first_line(exc)}\n"
                    "Run `python -m agent.main --doctor`. This is a platform problem, not your code.",
                    pytrace=False)
    return True


@pytest.fixture(scope="session")
def policy_index(qdrant):
    """The policy index, built once per test session by YOUR build_index()."""
    from services.vector_client import build_index
    return build_index()


@pytest.fixture(scope="session")
def fuseki(settings):
    import httpx
    try:
        response = httpx.post(settings.sparql_endpoint, data={"query": "ASK { ?s ?p ?o }"},
                              headers={"Accept": "application/sparql-results+json"},
                              timeout=settings.http_timeout_s)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"The knowledge graph is not reachable at {settings.sparql_endpoint or '(not set)'}: "
                    f"{_first_line(exc)}\nRun `python -m agent.main --doctor`. "
                    "This is a platform problem, not your code.", pytrace=False)
    return True


@pytest.fixture(scope="session")
def gateway(settings):
    """Fails - with the reason - if the model gateway cannot be used."""
    if not settings.api_key:
        pytest.fail("No gateway key: OPENAI_API_KEY is empty. Put your key (sk-bf-...) in .env.",
                    pytrace=False)
    if not settings.gateway_url:
        pytest.fail("OPENAI_BASE_URL is empty - the gateway address was not injected. Tell your trainer.",
                    pytrace=False)
    return True


@pytest.fixture()
def evidence():
    """A clean evidence log for one test."""
    from agent.evidence import EVIDENCE
    EVIDENCE.reset()
    yield EVIDENCE
    EVIDENCE.reset()


def table_signature() -> tuple:
    """Row count and checksums of student_performance - to prove nothing was modified."""
    from services.dataset_service import connect
    with connect() as conn:
        return tuple(conn.execute(
            "SELECT count(*), coalesce(sum(marks), 0), coalesce(sum(attendance), 0) "
            "FROM student_performance").fetchone())
