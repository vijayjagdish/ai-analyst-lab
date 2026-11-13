"""Milestone 4 - index the policy documents in Qdrant and search them.        ./check.sh 4

Code under test: services/vector_client.py -> chunk_markdown(), build_index(), search()
"""

from __future__ import annotations

import pytest

from services import vector_client

SAMPLE = """# Sample Policy

An introduction that belongs to no rule and must not be indexed.

## XR-1 First rule

The first rule has two lines.
This is its second line.

### A sub-heading inside the first rule

Sub-headings stay inside their chunk.

## XR-2 Second rule

- a bullet
- another bullet
"""

# (question, rule that must come back in the top 3)
RETRIEVAL = [
    ("What is the pass mark for a laboratory paper?", "AR-2"),
    ("How are absent students treated when an average is calculated?", "AR-3"),
    ("How is the pass percentage of a department calculated?", "AR-5"),
    ("Which students need academic attention?", "SS-1"),
    ("When is a student considered at risk?", "SS-2"),
    ("What is the minimum attendance requirement?", "AT-1"),
    ("Who should a failing student be referred to?", "SS-4"),
    ("How many backlogs stop a student being promoted?", "AR-7"),
    ("What does it take to be on the Dean's merit list?", "SS-6"),
    ("What does an empty attendance value mean?", "AT-3"),
]

CHUNK_KEYS = {"chunk_id", "doc", "rule_id", "section", "text"}
HIT_KEYS = {"rule_id", "doc", "section", "text", "score"}


def test_chunker_makes_one_chunk_per_level_two_heading():
    chunks = vector_client.chunk_markdown(SAMPLE, doc="sample")
    assert [c.get("rule_id") for c in chunks] == ["XR-1", "XR-2"], (
        f"expected two chunks (XR-1, XR-2), got {[c.get('rule_id') for c in chunks]}. "
        "Only lines starting with '## ' open a chunk; '### ' is a sub-heading and stays inside.")
    for chunk in chunks:
        assert set(chunk) == CHUNK_KEYS, f"a chunk needs exactly the keys {sorted(CHUNK_KEYS)}, got {sorted(chunk)}"


def test_chunk_fields_are_built_as_specified():
    first, second = vector_client.chunk_markdown(SAMPLE, doc="sample")
    assert first["chunk_id"] == "sample#XR-1" and first["doc"] == "sample"
    assert first["section"] == "XR-1 First rule", f"section should be the heading without '## ', got {first['section']!r}"
    assert first["text"].startswith("XR-1 First rule\n\nThe first rule has two lines."), (
        f"text must be the heading, a blank line, then the body. Got: {first['text'][:80]!r}")
    assert "### A sub-heading inside the first rule" in first["text"], "sub-headings belong to their chunk"
    assert first["text"].endswith("Sub-headings stay inside their chunk."), "the body must be stripped of trailing blank lines"
    assert second["text"] == "XR-2 Second rule\n\n- a bullet\n- another bullet"


def test_text_before_the_first_heading_is_dropped():
    chunks = vector_client.chunk_markdown(SAMPLE, doc="sample")
    assert not any("introduction" in c["text"] for c in chunks), (
        "the title and intro above the first '## ' heading are not a rule and must not be indexed")
    assert vector_client.chunk_markdown("# Only a title\n\nNo rules here.\n", doc="empty") == []


def test_the_whole_corpus_chunks_into_39_rules(settings):
    chunks = []
    for path in sorted(settings.policies_dir.glob("*.md")):
        chunks.extend(vector_client.chunk_markdown(path.read_text(encoding="utf-8"), doc=path.stem))
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == 39, f"the five policy documents contain 39 rules, the chunker produced {len(ids)}"
    assert len(set(ids)) == 39, "chunk ids must be unique"
    assert "academic-regulations#AR-2" in ids and "campus-handbook#CH-10" in ids


def test_build_index_stores_every_chunk_once(policy_index, settings):
    assert policy_index == 39, f"build_index() returned {policy_index}, expected 39 points in the collection"
    again = vector_client.build_index()
    assert again == 39, (
        f"building the index a second time left {again} points; it must still be 39. "
        "Use point_id(chunk_id) as the id and clear the old points first.")


def test_stale_points_are_removed_on_rebuild(policy_index, settings):
    from qdrant_client import models

    client = vector_client.get_client()
    client.upsert(settings.qdrant_collection, wait=True, points=[models.PointStruct(
        id=vector_client.point_id("retired#OLD-1"),
        vector=vector_client.embed(["a retired rule about pass marks"])[0],
        payload={"chunk_id": "retired#OLD-1", "doc": "retired", "rule_id": "OLD-1",
                 "section": "OLD-1 Retired rule", "text": "a retired rule about pass marks"})])
    assert vector_client.build_index() == 39, (
        "a point that no longer corresponds to any chunk survived a rebuild. "
        "Delete the existing points before upserting the current ones.")


def test_search_returns_scored_hits(policy_index):
    hits = vector_client.search("pass mark", k=3)
    assert isinstance(hits, list) and len(hits) == 3, f"asked for 3 hits, got {len(hits) if isinstance(hits, list) else hits!r}"
    for hit in hits:
        assert set(hit) == HIT_KEYS, f"a hit needs exactly the keys {sorted(HIT_KEYS)}, got {sorted(hit)}"
        assert isinstance(hit["score"], float), "score must be a float"
    scores = [hit["score"] for hit in hits]
    assert scores == sorted(scores, reverse=True), f"hits must be ordered best first, got scores {scores}"


@pytest.mark.parametrize("question, rule", RETRIEVAL)
def test_search_finds_the_rule_that_answers_the_question(policy_index, question, rule):
    hits = vector_client.search(question, k=3)
    found = [hit["rule_id"] for hit in hits]
    assert rule in found, (
        f"{question!r} should retrieve {rule} in the top 3, got {found}.\n"
        "Check that the heading is part of the embedded text and that questions and "
        "documents go through the same embed().")


def test_search_can_be_restricted_to_one_document(policy_index):
    hits = vector_client.search("minimum percentage required", k=4, doc="attendance-policy")
    docs = {hit["doc"] for hit in hits}
    assert hits and docs == {"attendance-policy"}, (
        f"with doc='attendance-policy' every hit must come from that document, got {sorted(docs)}")
