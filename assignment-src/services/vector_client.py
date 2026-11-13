"""Qdrant: turning the policy documents into something the agent can search.

The college's rules - what counts as a pass, how an absent student is treated,
who needs academic attention - are written in the Markdown files under
knowledge/policies/. They are NOT in the database and NOT in your prompt. The
agent has to find the right rule at the moment it needs it. That is retrieval:

    chunk_markdown()   split a document into rule-sized pieces     Milestone 4
    build_index()      embed every piece and store it in Qdrant    Milestone 4
    search()           embed a question, return the nearest rules  Milestone 4

You have your own Qdrant collection (QDRANT_COLLECTION). It was created for you
by the platform, empty; your key can read and write the points in it and
nothing else on the server.

Embeddings are computed INSIDE your container by a small model that is baked
into the image (BAAI/bge-small-en-v1.5, 384 dimensions). No network call, no
token cost, and the same text always maps to the same vector - which is what
lets a test say "this question must retrieve rule AR-2".
"""

from __future__ import annotations

import atexit
import uuid
import warnings
from functools import lru_cache
from pathlib import Path

from .config import get_settings

# In-cluster traffic to Qdrant is plain HTTP by design; the client's warning
# about sending a key over an insecure connection is correct in general and
# noise here.
warnings.filterwarnings("ignore", message="Api key is used with an insecure connection")


@lru_cache(maxsize=1)
def get_client():
    """The Qdrant client for your collection.  (PROVIDED)

    QDRANT_URL=":memory:" gives a throwaway in-process Qdrant - handy for trying
    the chunker with no server, useless for anything you want to keep.
    """
    from qdrant_client import QdrantClient

    settings = get_settings()
    settings.require("qdrant_url", "qdrant_collection")
    if settings.qdrant_url == ":memory:":
        return QdrantClient(":memory:")
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=settings.http_timeout_s,
        check_compatibility=False,
    )
    # Close the connection pool while the interpreter is still whole; left to
    # garbage collection at shutdown it prints a spurious warning.
    atexit.register(client.close)
    return client


@lru_cache(maxsize=1)
def _embedder():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=get_settings().embedding_model)


def embed(texts: list[str]) -> list[list[float]]:
    """Turn texts into vectors, one list of floats per text.  (PROVIDED)

    The first call loads the model (a second or two); after that it is fast.
    Documents and questions go through the SAME function. If they were embedded
    by different models the distances between them would be meaningless.
    """
    return [vector.tolist() for vector in _embedder().embed(list(texts))]


def point_id(chunk_id: str) -> str:
    """A stable Qdrant point id for a chunk.  (PROVIDED)

    Qdrant ids must be integers or UUIDs. Deriving the UUID from the chunk id
    makes indexing idempotent: index the same chunk twice and you overwrite the
    point instead of adding a duplicate.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ccit-policy/{chunk_id}"))


def chunk_markdown(text: str, doc: str) -> list[dict]:
    """Split one policy document into chunks, one per level-2 heading.

    Each `## ` heading starts a chunk that runs to the next `## ` heading (or the
    end of the file). Anything before the first `## ` - the title and intro - is
    dropped.

    Args:
        text: the Markdown source.
        doc: the document's name, i.e. the file name without `.md`.

    Returns:
        A list of dicts, in document order, each with exactly these keys:
            chunk_id   f"{doc}#{rule_id}"                e.g. "academic-regulations#AR-2"
            doc        the `doc` argument
            rule_id    the first word of the heading     e.g. "AR-2"
            section    the full heading without "## "    e.g. "AR-2 Pass marks"
            text       section + blank line + the body, with the body stripped
    """
    # >>> TODO M4-1 ─────────────────────────────────────────────────────────
    # Walk the lines. A line that starts with "## " (two hashes and a space -
    # "### " is a sub-heading and stays inside its chunk) closes the current
    # chunk and opens a new one.
    #
    # Why chunk by heading instead of every N characters: each section here is
    # ONE rule. A fixed-size window would cut "Laboratory paper: at least 50"
    # away from the heading that says it is about pass marks, and the vector
    # for the fragment would no longer be about anything in particular.
    #
    # Why the heading goes INTO the text that gets embedded: "AR-2 Pass marks"
    # is the best summary of the chunk that exists. Leave it out and you throw
    # away the words most likely to match the question.
    # >>> SOLUTION
    chunks: list[dict] = []
    heading: str | None = None
    body: list[str] = []

    def close() -> None:
        if heading is None:
            return
        rule_id = heading.split()[0]
        chunks.append({
            "chunk_id": f"{doc}#{rule_id}",
            "doc": doc,
            "rule_id": rule_id,
            "section": heading,
            "text": f"{heading}\n\n" + "\n".join(body).strip(),
        })

    for line in text.splitlines():
        if line.startswith("## "):
            close()
            heading = line[3:].strip()
            body = []
        elif heading is not None:
            body.append(line)
    close()
    return chunks
    # <<< END TODO


def build_index(policies_dir: Path | str | None = None) -> int:
    """Chunk, embed and store every policy document in your Qdrant collection.

    Safe to run again: afterwards the collection holds exactly the current
    chunks, however many times it has been built.

    Args:
        policies_dir: folder of `.md` files; defaults to knowledge/policies.

    Returns:
        The number of points in the collection after indexing.
    """
    from qdrant_client import models

    settings = get_settings()
    policies_dir = Path(policies_dir) if policies_dir else settings.policies_dir
    client = get_client()
    collection = settings.qdrant_collection

    # >>> TODO M4-2 ─────────────────────────────────────────────────────────
    #   1. For every *.md file in policies_dir (sorted, so the order is
    #      stable), read it and chunk it with chunk_markdown(text, doc=path.stem).
    #   2. embed() the "text" of every chunk - one call for the whole list is
    #      much faster than one call per chunk.
    #   3. If the collection does not exist, create it:
    #          client.create_collection(collection, vectors_config=models.VectorParams(
    #              size=settings.embedding_dim, distance=models.Distance.COSINE))
    #      On the platform it already exists (your key may not create
    #      collections), so this branch only runs on a private Qdrant.
    #   4. Delete the points that are already there:
    #          client.delete(collection, points_selector=models.FilterSelector(
    #              filter=models.Filter()), wait=True)
    #      Without this, a chunk you renamed or removed stays searchable
    #      forever - the classic stale-index bug.
    #   5. client.upsert(collection, points=[...], wait=True) with one
    #      models.PointStruct(id=point_id(chunk["chunk_id"]), vector=..., payload=chunk)
    #      per chunk. The payload is what comes back from a search, so the whole
    #      chunk dict goes in.
    #   6. Return client.count(collection, exact=True).count
    # >>> SOLUTION
    chunks: list[dict] = []
    for path in sorted(policies_dir.glob("*.md")):
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), doc=path.stem))
    if not chunks:
        raise RuntimeError(f"no policy chunks found under {policies_dir}")

    vectors = embed([chunk["text"] for chunk in chunks])

    if not client.collection_exists(collection):
        client.create_collection(
            collection,
            vectors_config=models.VectorParams(size=settings.embedding_dim,
                                               distance=models.Distance.COSINE),
        )
    client.delete(collection, points_selector=models.FilterSelector(filter=models.Filter()),
                  wait=True)
    client.upsert(
        collection,
        points=[
            models.PointStruct(id=point_id(chunk["chunk_id"]), vector=vector, payload=chunk)
            for chunk, vector in zip(chunks, vectors)
        ],
        wait=True,
    )
    return client.count(collection, exact=True).count
    # <<< END TODO


def search(query: str, k: int = 4, doc: str | None = None) -> list[dict]:
    """Find the policy chunks closest in meaning to `query`.

    Args:
        query: a question or phrase in plain language.
        k: how many chunks to return.
        doc: if given, search only inside that document (e.g. "attendance-policy").

    Returns:
        Up to `k` dicts, best match first, each with the keys
        rule_id, doc, section, text and score (a float, higher is closer).
    """
    from qdrant_client import models

    settings = get_settings()
    client = get_client()

    # >>> TODO M4-3 ─────────────────────────────────────────────────────────
    #   1. Embed the query with the same embed() used for the documents.
    #   2. client.query_points(collection_name=..., query=<vector>, limit=k,
    #                          with_payload=True, query_filter=<filter or None>)
    #      For the `doc` restriction build:
    #          models.Filter(must=[models.FieldCondition(
    #              key="doc", match=models.MatchValue(value=doc))])
    #      That is a metadata filter: the similarity search only ever sees
    #      points whose payload matches. It is the same mechanism a real system
    #      uses to keep one tenant from retrieving another tenant's documents.
    #   3. The hits are in response.points; each has .payload and .score.
    #      Return plain dicts with the five keys from the docstring.
    # >>> SOLUTION
    vector = embed([query])[0]
    query_filter = None
    if doc:
        query_filter = models.Filter(
            must=[models.FieldCondition(key="doc", match=models.MatchValue(value=doc))])
    response = client.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        limit=int(k),
        with_payload=True,
        query_filter=query_filter,
    )
    return [
        {
            "rule_id": point.payload.get("rule_id"),
            "doc": point.payload.get("doc"),
            "section": point.payload.get("section"),
            "text": point.payload.get("text"),
            "score": round(float(point.score), 4),
        }
        for point in response.points
    ]
    # <<< END TODO
