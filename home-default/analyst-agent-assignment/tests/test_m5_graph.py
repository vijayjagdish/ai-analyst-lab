"""Milestone 5 - query the curriculum knowledge graph in Apache Jena Fuseki.        ./check.sh 5

Code under test: services/graph_client.py -> sparql_select(), prerequisites(),
                 dependents(), support_contacts()
"""

from __future__ import annotations

import pytest

from services import graph_client
from services.graph_client import PREFIXES, GraphError


def codes(rows: list[dict]) -> list[str]:
    return [row["code"] for row in rows]


def test_select_returns_one_dict_per_row(fuseki):
    rows = graph_client.sparql_select(PREFIXES + """
        SELECT ?code ?name ?semester WHERE {
          subj:CS301 cc:code ?code ; rdfs:label ?name ; cc:semester ?semester .
        }""")
    assert rows == [{"code": "CS301", "name": "Data Structures", "semester": 3}], (
        f"expected one row for CS301 with semester as the integer 3, got {rows!r}.\n"
        "Key each row by variable name and pass every cell through _convert().")


def test_unbound_variables_are_none_not_missing(fuseki):
    rows = graph_client.sparql_select(PREFIXES + """
        SELECT ?code ?prerequisite WHERE {
          subj:CS301 cc:code ?code .
          OPTIONAL { subj:CS301 cc:hasPrerequisite ?prerequisite }
        }""")
    assert rows == [{"code": "CS301", "prerequisite": None}], (
        f"CS301 has no prerequisite, so ?prerequisite is unbound and must come back as None. Got {rows!r}.\n"
        "Loop over head.vars, not over the keys of each binding.")


def test_a_broken_query_raises_grapherror(fuseki):
    with pytest.raises(GraphError) as caught:
        graph_client.sparql_select("SELEKT ?x WHERE { ?x ?y ?z }")
    assert "400" in str(caught.value) or "parse" in str(caught.value).lower(), (
        f"include the server's status and message in the GraphError, got: {caught.value}")


def test_an_empty_result_is_an_empty_list(fuseki):
    rows = graph_client.sparql_select(PREFIXES + "SELECT ?s WHERE { ?s cc:code \"NO-SUCH-CODE\" }")
    assert rows == []


@pytest.mark.parametrize("code", ["CS603", "CS401", "CS301"])
def test_transitive_prerequisites(fuseki, expected, code):
    want = expected["graph"]["prerequisites"][code]["transitive"]
    got = graph_client.prerequisites(code)
    assert codes(got) == codes(want), (
        f"prerequisites({code!r}) returned {codes(got)}, expected {codes(want)} "
        "(the whole chain, ordered by semester then code, each subject once).")
    assert got == want, f"codes are right but the rows differ.\n got: {got}\nwant: {want}"


@pytest.mark.parametrize("code", ["CS603", "CS401"])
def test_direct_prerequisites_only(fuseki, expected, code):
    want = expected["graph"]["prerequisites"][code]["direct"]
    got = graph_client.prerequisites(code, transitive=False)
    assert got == want, f"prerequisites({code!r}, transitive=False) returned {got}, expected {want}"
    assert all(row["direct"] is True for row in got), "every row of a direct-only result has direct=True"


@pytest.mark.parametrize("code", ["CS301", "CS605"])
def test_dependents_follow_the_chain_forwards(fuseki, expected, code):
    want = expected["graph"]["dependents"][code]
    got = graph_client.dependents(code)
    assert codes(got) == codes(want), (
        f"dependents({code!r}) returned {codes(got)}, expected {codes(want)}.\n"
        "Every subject that needs it, directly or through other subjects.")
    assert got == want, f"codes are right but the rows differ.\n got: {got}\nwant: {want}"


def test_lower_case_codes_are_accepted(fuseki, expected):
    assert codes(graph_client.dependents("cs301")) == codes(expected["graph"]["dependents"]["CS301"])


@pytest.mark.parametrize("code", ["CS301", "CS402"])
def test_support_contacts(fuseki, expected, code):
    want = expected["graph"]["support"][code]
    got = graph_client.support_contacts(code)
    assert set(got) == {"subject", "taught_by", "remedial_courses"}, (
        f"support_contacts() must return exactly subject, taught_by and remedial_courses - got {sorted(got)}")
    assert got["subject"] == want["subject"], f"subject: got {got['subject']}, expected {want['subject']}"
    assert got["taught_by"] == want["taught_by"], f"taught_by: got {got['taught_by']}, expected {want['taught_by']}"
    assert got["remedial_courses"] == want["remedial_courses"], (
        f"remedial_courses for {code}: got {got['remedial_courses']}, expected {want['remedial_courses']}.\n"
        "A subject with no bridge course has an EMPTY list - that is an answer, not an error.")


def test_an_unknown_subject_is_reported(fuseki):
    with pytest.raises(GraphError):
        graph_client.support_contacts("CS999")


def test_malformed_codes_never_reach_the_query(fuseki):
    assert graph_client.prerequisites("CS603"), "a valid code must return rows before this test means anything"
    assert graph_client.dependents("CS301")
    for bad in ["", "DROP", "CS301> ?p ?o } UNION { ?s ?p ?o", "subj:CS301", "CS3011"]:
        for function in (graph_client.prerequisites, graph_client.dependents, graph_client.support_contacts):
            with pytest.raises(GraphError):
                function(bad)
