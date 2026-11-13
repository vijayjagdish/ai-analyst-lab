"""HIDDEN - policy retrieval, with questions and a document the student has not seen.

Every question below retrieves its rule at rank 1 with the reference
implementation; the test asks only for the top 3, which leaves room for small
floating-point differences between machines but not for a broken index.
"""

from __future__ import annotations

import pytest

from services import vector_client

# (question, any one of these rules must be in the top 3)
RETRIEVAL = [
    ("What happens to the average when a student misses an examination?", ["AR-3"]),
    ("Can the raw marks of a laboratory paper and a theory paper be compared?", ["AR-1"]),
    ("What percentage is needed to pass a theory paper?", ["AR-2"]),
    ("How is the average attendance of a department calculated?", ["AT-4"]),
    ("Which students are placed on the priority counselling list?", ["SS-3"]),
    ("How is the semester aggregate of one student calculated?", ["AR-8"]),
    ("What do the columns of the subject_details table mean?", ["DD-3"]),
    ("Where are prerequisites and the teaching allocation stored?", ["DD-7", "SS-4", "SS-5"]),
    ("What letter grade does a percentage of 72 earn?", ["AR-6"]),
    ("Is a condonable attendance shortage different from a severe one?", ["AT-2"]),
    ("How long does a student have to apply for revaluation?", ["AR-9"]),
]

DOCUMENT = """# Hostel Mess Rules

Preamble text. It mentions ## in the middle of a line, which is not a heading.

##NotAHeading because there is no space after the hashes

## HM-1 Meal timings

Breakfast is served from 7 am.

#### A deeper heading stays inside

Dinner ends at 9 pm.

## HM-2 Guests

## HM-3 Feedback

One line only.
"""


@pytest.mark.parametrize("question, rules", RETRIEVAL)
def test_hidden_retrieval(policy_index, question, rules):
    found = [hit["rule_id"] for hit in vector_client.search(question, k=3)]
    assert set(found) & set(rules), f"{question!r} should retrieve one of {rules} in the top 3, got {found}"


def test_hidden_chunker_on_an_unseen_document():
    chunks = vector_client.chunk_markdown(DOCUMENT, doc="hostel-mess")
    assert [c["rule_id"] for c in chunks] == ["HM-1", "HM-2", "HM-3"], (
        f"expected HM-1, HM-2, HM-3 - got {[c.get('rule_id') for c in chunks]}. Only a line that STARTS "
        "with '## ' opens a chunk.")
    first, second, third = chunks
    assert first["chunk_id"] == "hostel-mess#HM-1"
    assert first["text"] == ("HM-1 Meal timings\n\nBreakfast is served from 7 am.\n\n"
                             "#### A deeper heading stays inside\n\nDinner ends at 9 pm.")
    assert second["section"] == "HM-2 Guests" and second["text"].strip() == "HM-2 Guests", (
        f"a heading with no body is still a chunk, holding just its heading: {second['text']!r}")
    assert third["text"] == "HM-3 Feedback\n\nOne line only."
    assert not any("Preamble" in c["text"] or "NotAHeading" in c["text"] for c in chunks)


def test_hidden_k_is_respected_and_scores_are_sensible(policy_index):
    for k in (1, 5, 8):
        hits = vector_client.search("attendance", k=k)
        assert len(hits) == k, f"search(k={k}) returned {len(hits)} hits"
    hits = vector_client.search("pass mark for laboratory papers", k=8)
    scores = [hit["score"] for hit in hits]
    assert scores == sorted(scores, reverse=True) and scores[0] > scores[-1], f"scores are not a ranking: {scores}"
    assert hits[0]["rule_id"] == "AR-2", f"the closest rule to 'pass mark for laboratory papers' is AR-2, got {hits[0]['rule_id']}"


def test_hidden_document_filter_is_a_real_filter(policy_index):
    """An unrelated document must still return ONLY its own chunks, however poor the match."""
    hits = vector_client.search("pass mark for laboratory papers", k=5, doc="campus-handbook")
    assert len(hits) == 5 and {hit["doc"] for hit in hits} == {"campus-handbook"}, (
        f"doc='campus-handbook' must restrict the search to that document, got {[h['rule_id'] for h in hits]}")
    assert vector_client.search("anything", k=3, doc="no-such-document") == []


def test_hidden_index_holds_only_the_five_documents(policy_index, settings):
    client = vector_client.get_client()
    points, _ = client.scroll(settings.qdrant_collection, limit=200, with_payload=True)
    docs = sorted({point.payload.get("doc") for point in points})
    assert len(points) == 39 and docs == ["academic-regulations", "attendance-policy", "campus-handbook",
                                          "data-dictionary", "student-support-policy"], (
        f"the collection holds {len(points)} points from {docs}")
    for point in points:
        assert set(point.payload) >= {"chunk_id", "doc", "rule_id", "section", "text"}, (
            f"a stored point is missing payload fields: {sorted(point.payload)}")
