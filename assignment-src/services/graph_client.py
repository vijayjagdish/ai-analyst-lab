"""Apache Jena Fuseki: asking the curriculum knowledge graph how things connect.

The database knows what marks a student got. It does not know that Machine
Learning cannot be taken without Algorithms, that Algorithms needs Data
Structures, who teaches any of them, or which bridge course exists for a
student who failed one. Those are RELATIONSHIPS, and they live in a knowledge
graph served by Apache Jena Fuseki - one shared, read-only graph for everybody.

You query it with SPARQL over HTTP. The schema is described in
knowledge/graph/ONTOLOGY.md; read that before writing a query.

    sparql_select()       send a SELECT, get rows back            Milestone 5
    find_subjects()       look a subject up by code or name       provided
    prerequisites()       what a subject depends on               Milestone 5
    dependents()          what depends on a subject               Milestone 5
    support_contacts()    who to refer a struggling student to    Milestone 5
    career_track()        subjects that build a career's skills   provided

Why these are fixed query TEMPLATES and not "let the model write SPARQL": the
questions the graph is asked are few and known in advance, so a template with
one validated parameter is both more reliable and safer than free-form text.
Compare agent/sql_guard.py, where the questions are open-ended and the model
does write the query - and a whole module exists to police it.
"""

from __future__ import annotations

import atexit
import re
from functools import lru_cache

import httpx

from .config import get_settings

PREFIXES = """\
PREFIX cc:   <https://kg.cream-collar.com/campus/ontology#>
PREFIX subj: <https://kg.cream-collar.com/campus/subject/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

SUBJECT_CODE = re.compile(r"[A-Z]{2}[0-9]{3}")

_XSD = "http://www.w3.org/2001/XMLSchema#"
_INTEGER_TYPES = {_XSD + name for name in ("integer", "int", "long", "short", "nonNegativeInteger")}
_FLOAT_TYPES = {_XSD + name for name in ("decimal", "double", "float")}


class GraphError(RuntimeError):
    """The knowledge graph could not answer: bad input, a bad query, or the server is down."""


@lru_cache(maxsize=1)
def http_client() -> httpx.Client:
    """One HTTP client for the whole process.  (PROVIDED)

    Building a client is the expensive part of a request - it sets up TLS state
    and a connection pool. `httpx.post(...)` builds and throws away a new one on
    every call; an agent that makes five graph lookups to answer one question
    would pay that five times. One shared client keeps each lookup to a few
    milliseconds, and it is safe to use from the worker threads tools run on.
    """
    client = httpx.Client(timeout=get_settings().http_timeout_s)
    atexit.register(client.close)
    return client


def subject_iri(subject_code: str) -> str:
    """Return the prefixed name of a subject, e.g. 'subj:CS301'.  (PROVIDED)

    This is the ONLY way a subject code gets into a query. The code is matched
    against a strict pattern first, so what is spliced into the SPARQL text can
    never be anything but two letters and three digits. Injection is not a
    SQL-only problem: a "code" such as
        CS301> ?p ?o } UNION { ?s ?p ?o
    pasted into a query would rewrite it.
    """
    code = str(subject_code).strip().upper()
    if not SUBJECT_CODE.fullmatch(code):
        raise GraphError(f"{subject_code!r} is not a subject code (expected something like CS301)")
    return f"subj:{code}"


def literal(text: str) -> str:
    """Quote free text as a SPARQL string literal.  (PROVIDED)"""
    escaped = (str(text).replace("\\", "\\\\").replace('"', '\\"')
               .replace("\n", "\\n").replace("\r", "\\r"))
    return f'"{escaped}"'


def _convert(cell: dict | None):
    """One cell of a SPARQL JSON result -> a plain Python value.  (PROVIDED)"""
    if cell is None:
        return None
    value, datatype = cell.get("value"), cell.get("datatype")
    if datatype in _INTEGER_TYPES:
        return int(value)
    if datatype in _FLOAT_TYPES:
        return float(value)
    if datatype == _XSD + "boolean":
        return value == "true"
    return value


def sparql_select(query: str) -> list[dict]:
    """Run a SPARQL SELECT against the knowledge graph and return its rows.

    Args:
        query: a complete SELECT query, prefixes included.

    Returns:
        One dict per result row, keyed by variable name (without the '?').
        Every variable in the SELECT clause is present in every row; a variable
        that is unbound in a row has the value None. Numbers and booleans are
        converted to Python types.

    Raises:
        GraphError: the server refused the query or could not be reached.
    """
    settings = get_settings()
    settings.require("sparql_endpoint")

    # >>> TODO M5-1 ─────────────────────────────────────────────────────────
    # The SPARQL protocol is plain HTTP:
    #
    #   POST <endpoint>
    #   Content-Type: application/x-www-form-urlencoded     (httpx: data={"query": query})
    #   Accept: application/sparql-results+json
    #
    # and the answer is JSON shaped like
    #
    #   {"head": {"vars": ["code", "name"]},
    #    "results": {"bindings": [
    #        {"code": {"type": "literal", "value": "CS301"},
    #         "name": {"type": "literal", "value": "Data Structures"}}, ...]}}
    #
    #   1. http_client().post(settings.sparql_endpoint, data=..., headers=...)
    #      Use the shared client above rather than httpx.post() - see its
    #      docstring for why.
    #   2. A status of 400 or above is a failure: raise GraphError and include
    #      response.text - Fuseki puts the parse error there, and you want to
    #      see it. httpx.HTTPError (connection refused, timeout) -> GraphError
    #      too.
    #   3. Build one dict per binding. Loop over head.vars, NOT over the
    #      binding's own keys: an OPTIONAL variable that did not match is simply
    #      absent from the binding, and callers should get None for it instead
    #      of a KeyError. Pass each cell through _convert().
    #
    # Always send the Accept header. Without it Fuseki may answer in XML.
    # >>> SOLUTION
    try:
        response = http_client().post(
            settings.sparql_endpoint,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
        )
    except httpx.HTTPError as exc:
        raise GraphError(f"could not reach the knowledge graph at {settings.sparql_endpoint}: {exc}") from exc
    if response.status_code >= 400:
        raise GraphError(
            f"the knowledge graph refused the query (HTTP {response.status_code}): {response.text.strip()[:400]}")

    payload = response.json()
    variables = payload.get("head", {}).get("vars", [])
    return [
        {name: _convert(binding.get(name)) for name in variables}
        for binding in payload.get("results", {}).get("bindings", [])
    ]
    # <<< END TODO


def find_subjects(text: str) -> list[dict]:
    """Look subjects up by exact code or by part of their name.  (PROVIDED - a worked example)

    Returns dicts with code, name, department, semester, subject_type, ordered
    by code. "Data Structures" matches CS301, CS305 and IT301: titles are not
    unique, which is why every other function here takes a CODE.
    """
    needle = literal(text.strip())
    query = PREFIXES + f"""
SELECT ?code ?name ?department ?semester ?subject_type WHERE {{
  ?s a cc:Subject ;
     cc:code ?code ;
     rdfs:label ?name ;
     cc:semester ?semester ;
     cc:subjectType ?subject_type ;
     cc:offeredBy/cc:code ?department .
  FILTER (LCASE(?code) = LCASE({needle}) || CONTAINS(LCASE(?name), LCASE({needle})))
}}
ORDER BY ?code
"""
    return sparql_select(query)


def prerequisites(subject_code: str, transitive: bool = True) -> list[dict]:
    """The subjects that `subject_code` depends on.

    Args:
        subject_code: e.g. "CS603".
        transitive: True (default) follows the whole chain - prerequisites of
            prerequisites and so on. False returns only the direct ones.

    Returns:
        Dicts with code, name, semester and direct (True when the subject is an
        immediate prerequisite), ordered by semester then code. No duplicates.
    """
    subject = subject_iri(subject_code)

    # >>> TODO M5-2 ─────────────────────────────────────────────────────────
    # The graph stores only DIRECT prerequisites:
    #     subj:CS603 cc:hasPrerequisite subj:CS503 .
    #     subj:CS503 cc:hasPrerequisite subj:CS401 , subj:CS404 .
    #
    # A SPARQL property path follows an edge repeatedly:
    #     subj:CS603 cc:hasPrerequisite+ ?p      ("+" = one or more hops)
    # In SQL this is a recursive CTE. In a graph query language it is one
    # character - which is the reason this data is in a graph at all.
    #
    #   1. Use the path `cc:hasPrerequisite+` when transitive, plain
    #      `cc:hasPrerequisite` when not.
    #   2. For each ?p fetch cc:code, rdfs:label (as ?name) and cc:semester.
    #   3. Tell direct from indirect inside the query:
    #          BIND (EXISTS { <subject> cc:hasPrerequisite ?p } AS ?direct)
    #   4. SELECT DISTINCT - a subject reachable by two routes must appear once.
    #      ORDER BY ?semester ?code.
    #   5. Start the query with PREFIXES and run it with sparql_select().
    #
    # `subject` above is already safe to splice in; see subject_iri().
    # >>> SOLUTION
    path = "cc:hasPrerequisite+" if transitive else "cc:hasPrerequisite"
    query = PREFIXES + f"""
SELECT DISTINCT ?code ?name ?semester ?direct WHERE {{
  {subject} {path} ?p .
  ?p cc:code ?code ;
     rdfs:label ?name ;
     cc:semester ?semester .
  BIND (EXISTS {{ {subject} cc:hasPrerequisite ?p }} AS ?direct)
}}
ORDER BY ?semester ?code
"""
    return sparql_select(query)
    # <<< END TODO


def dependents(subject_code: str) -> list[dict]:
    """Every later subject that depends on `subject_code`, directly or through a chain.

    This is the "what is at risk next?" question: a student with a backlog in
    CS301 is at prerequisite risk in every subject returned here.

    Returns:
        Dicts with code, name, semester and direct (True when `subject_code` is
        an immediate prerequisite of that subject), ordered by semester then
        code. No duplicates.
    """
    subject = subject_iri(subject_code)

    # >>> TODO M5-3 ─────────────────────────────────────────────────────────
    # Same edge as prerequisites(), walked the other way: find every ?s such
    # that
    #     ?s cc:hasPrerequisite+ <subject>
    # A triple pattern can have the variable on either side, so "who points at
    # me, through any number of hops" needs no new machinery.
    #
    # Return the same four columns: code, name, semester, direct.
    # >>> SOLUTION
    query = PREFIXES + f"""
SELECT DISTINCT ?code ?name ?semester ?direct WHERE {{
  ?s cc:hasPrerequisite+ {subject} .
  ?s cc:code ?code ;
     rdfs:label ?name ;
     cc:semester ?semester .
  BIND (EXISTS {{ ?s cc:hasPrerequisite {subject} }} AS ?direct)
}}
ORDER BY ?semester ?code
"""
    return sparql_select(query)
    # <<< END TODO


def support_contacts(subject_code: str) -> dict:
    """Where a student who needs academic attention in a subject is referred.

    Returns a dict with exactly three keys:

        subject           {"code", "name", "department", "semester"}
        taught_by         {"name", "designation", "email"}
        remedial_courses  a list (possibly empty), ordered by title, of
                          {"title", "coordinator", "coordinator_email",
                           "duration_weeks", "mode", "seat_limit"}

    Raises:
        GraphError: the subject code does not exist in the graph.
    """
    subject = subject_iri(subject_code)

    # >>> TODO M5-4 ─────────────────────────────────────────────────────────
    # Two queries, then shape the rows into the dict above.
    #
    #   Query 1 - the subject and its teacher (exactly one row):
    #       <subject> cc:code, rdfs:label, cc:semester,
    #                 cc:offeredBy/cc:code      (a path: department node -> its code)
    #                 cc:taughtBy ?f .
    #       ?f rdfs:label, cc:designation, cc:email .
    #     No row at all means the code is not in the graph -> raise GraphError.
    #
    #   Query 2 - remedial courses that support it (zero or more rows):
    #       ?r a cc:RemedialCourse ; cc:supports <subject> ; rdfs:label ;
    #          cc:coordinatedBy ?c ; cc:durationWeeks ; cc:mode ; cc:seatLimit .
    #       ?c rdfs:label ; cc:email .
    #     ORDER BY the course title.
    #
    # Why two queries instead of one with OPTIONAL: a subject can have several
    # remedial courses, and one joined query would repeat the teacher on every
    # row and leave you un-flattening it. Two small queries that each return
    # one shape are easier to get right.
    #
    # An empty remedial_courses list is a real answer, not an error: the policy
    # says such a student is referred to the teaching faculty instead.
    # >>> SOLUTION
    rows = sparql_select(PREFIXES + f"""
SELECT ?code ?name ?department ?semester ?faculty ?designation ?email WHERE {{
  {subject} cc:code ?code ;
            rdfs:label ?name ;
            cc:semester ?semester ;
            cc:offeredBy/cc:code ?department ;
            cc:taughtBy ?f .
  ?f rdfs:label ?faculty ;
     cc:designation ?designation ;
     cc:email ?email .
}}
""")
    if not rows:
        raise GraphError(f"subject {subject_code!r} is not in the knowledge graph")
    head = rows[0]

    courses = sparql_select(PREFIXES + f"""
SELECT ?title ?coordinator ?coordinator_email ?duration_weeks ?mode ?seat_limit WHERE {{
  ?r a cc:RemedialCourse ;
     cc:supports {subject} ;
     rdfs:label ?title ;
     cc:coordinatedBy ?c ;
     cc:durationWeeks ?duration_weeks ;
     cc:mode ?mode ;
     cc:seatLimit ?seat_limit .
  ?c rdfs:label ?coordinator ;
     cc:email ?coordinator_email .
}}
ORDER BY ?title
""")
    return {
        "subject": {"code": head["code"], "name": head["name"],
                    "department": head["department"], "semester": head["semester"]},
        "taught_by": {"name": head["faculty"], "designation": head["designation"],
                      "email": head["email"]},
        "remedial_courses": courses,
    }
    # <<< END TODO


def career_track(track_name: str, department: str | None = None) -> dict:
    """The skills a career track needs and the subjects that build them.  (PROVIDED - a worked example)

    A two-hop walk: track -> requiresSkill -> skill <- develops <- subject.

    Args:
        track_name: e.g. "Data Scientist" (case-insensitive).
        department: optional department code to keep only that department's subjects.

    Returns:
        {"track": name or None, "skills": [...], "subjects": [{code, name,
        department, semester, skill}, ...], "available_tracks": [...]}.
        When the track is unknown, "track" is None and "available_tracks" lists
        the valid names - so the caller can correct itself instead of guessing.
    """
    wanted = literal(track_name.strip())
    dept_filter = ""
    if department:
        dept_filter = f"FILTER (?department = {literal(department.strip().upper())})"
    rows = sparql_select(PREFIXES + f"""
SELECT ?track ?skill ?code ?name ?department ?semester WHERE {{
  ?t a cc:CareerTrack ;
     rdfs:label ?track ;
     cc:requiresSkill ?sk .
  FILTER (LCASE(?track) = LCASE({wanted}))
  ?sk rdfs:label ?skill .
  ?s cc:develops ?sk ;
     cc:code ?code ;
     rdfs:label ?name ;
     cc:semester ?semester ;
     cc:offeredBy/cc:code ?department .
  {dept_filter}
}}
ORDER BY ?skill ?semester ?code
""")
    tracks = [row["track"] for row in sparql_select(PREFIXES + """
SELECT ?track WHERE { ?t a cc:CareerTrack ; rdfs:label ?track } ORDER BY ?track
""")]
    if not rows:
        known = next((t for t in tracks if t.lower() == track_name.strip().lower()), None)
        return {"track": known, "skills": [], "subjects": [], "available_tracks": tracks}
    return {
        "track": rows[0]["track"],
        "skills": sorted({row["skill"] for row in rows}),
        "subjects": [{key: row[key] for key in ("code", "name", "department", "semester", "skill")}
                     for row in rows],
        "available_tracks": tracks,
    }
