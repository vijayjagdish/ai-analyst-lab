"""HIDDEN - knowledge-graph functions, on subjects the public tests never mention.

The public checkpoint uses CS301, CS401, CS603 and CS605. A solution that
special-cases those passes there and fails here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services import graph_client
from services.graph_client import PREFIXES, GraphError

EXPECTED = json.loads((Path(__file__).parent / "expected_hidden.json").read_text(encoding="utf-8"))["graph"]


def codes(rows: list[dict]) -> list[str]:
    return [row["code"] for row in rows]


@pytest.mark.parametrize("code", sorted(EXPECTED["prerequisites"]))
def test_hidden_transitive_prerequisites(fuseki, code):
    want = EXPECTED["prerequisites"][code]["transitive"]
    got = graph_client.prerequisites(code)
    assert codes(got) == codes(want), f"prerequisites({code!r}): got {codes(got)}, expected {codes(want)}"
    assert got == want, f"prerequisites({code!r}): codes match but rows differ\n got: {got}\nwant: {want}"


@pytest.mark.parametrize("code", sorted(EXPECTED["prerequisites"]))
def test_hidden_direct_prerequisites(fuseki, code):
    want = EXPECTED["prerequisites"][code]["direct"]
    got = graph_client.prerequisites(code, transitive=False)
    assert got == want, f"prerequisites({code!r}, transitive=False): got {got}, expected {want}"


@pytest.mark.parametrize("code", sorted(EXPECTED["dependents"]))
def test_hidden_dependents(fuseki, code):
    want = EXPECTED["dependents"][code]
    got = graph_client.dependents(code)
    assert codes(got) == codes(want), f"dependents({code!r}): got {codes(got)}, expected {codes(want)}"
    assert got == want, f"dependents({code!r}): codes match but rows differ\n got: {got}\nwant: {want}"


@pytest.mark.parametrize("code", sorted(EXPECTED["support"]))
def test_hidden_support_contacts(fuseki, code):
    want = EXPECTED["support"][code]
    got = graph_client.support_contacts(code)
    assert got == want, f"support_contacts({code!r}):\n got: {got}\nwant: {want}"


def test_hidden_select_handles_numbers_booleans_and_unbound(fuseki):
    rows = graph_client.sparql_select(PREFIXES + """
        SELECT ?code ?credits ?is_lab ?prerequisite WHERE {
          VALUES ?s { subj:ME305 subj:ME401 }
          ?s cc:code ?code ; cc:credits ?credits ; cc:subjectType ?type .
          BIND (?type = "Lab" AS ?is_lab)
          OPTIONAL { ?s cc:hasPrerequisite/cc:code ?prerequisite }
        } ORDER BY ?code""")
    assert rows == [
        {"code": "ME305", "credits": 2, "is_lab": True, "prerequisite": None},
        {"code": "ME401", "credits": 4, "is_lab": False, "prerequisite": "ME301"},
    ], f"typed values and unbound variables are not converted as specified: {rows}"


def test_hidden_the_graph_is_not_modified_by_anything_the_client_sends(fuseki):
    def triples() -> int:
        return graph_client.sparql_select("SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }")[0]["n"]

    before = triples()
    with pytest.raises(GraphError):
        graph_client.sparql_select("DELETE WHERE { ?s ?p ?o }")
    with pytest.raises(GraphError):
        graph_client.sparql_select(PREFIXES + "INSERT DATA { subj:XX999 cc:code \"XX999\" }")
    assert triples() == before


def test_hidden_unreachable_server_is_a_grapherror(fuseki, monkeypatch):
    from services.config import get_settings

    monkeypatch.setenv("SPARQL_ENDPOINT", "http://127.0.0.1:9/campus/sparql")
    get_settings(reload=True)
    try:
        with pytest.raises(GraphError):
            graph_client.sparql_select("SELECT * WHERE { ?s ?p ?o } LIMIT 1")
    finally:
        monkeypatch.delenv("SPARQL_ENDPOINT")
        get_settings(reload=True)
