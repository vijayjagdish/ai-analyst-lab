# The curriculum knowledge graph

The graph is served by **Apache Jena Fuseki**, outside your container, and is
shared by every student. It is **read-only**: you can query it, nobody can
change it. Your code reaches it at `$FUSEKI_URL/campus/sparql` (see
`services/config.py`) using the SPARQL protocol over HTTP.

It holds what the PostgreSQL tables do not: how subjects depend on each other,
who teaches them, which skills they build, which careers need those skills, and
which remedial courses exist. It also covers **semesters 5 and 6**, which have
no marks yet.

Subject codes (`CS301`) and department codes (`CSE`) are the same here as in
the tables. A code you get from SQL can be looked up in the graph, and the
reverse — that shared key is what lets the agent combine the two.

## Prefixes

```sparql
PREFIX cc:   <https://kg.cream-collar.com/campus/ontology#>
PREFIX subj: <https://kg.cream-collar.com/campus/subject/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
```

A subject's node is `subj:` followed by its code: `subj:CS301`.
`services/graph_client.PREFIXES` already contains these three lines.

## Classes

| Class | What it is | How many |
|---|---|---|
| `cc:Department` | An academic department | 5 |
| `cc:Subject` | A course, identified by its code | 100 (semesters 3–6) |
| `cc:Faculty` | A member of the teaching staff | 30 |
| `cc:Skill` | A competency subjects develop | 33 |
| `cc:CareerTrack` | A job role, described by the skills it needs | 12 |
| `cc:RemedialCourse` | A short bridge course for struggling students | 10 |

Every node has an `rdfs:label` — its human-readable name.

## Properties

| Property | From → To | Meaning |
|---|---|---|
| `cc:code` | Subject / Department → text | The code used in the PostgreSQL tables |
| `cc:offeredBy` | Subject → Department | The department that runs the subject |
| `cc:semester` | Subject → integer | 3, 4, 5 or 6 |
| `cc:credits` | Subject → integer | Credit value |
| `cc:subjectType` | Subject → text | `"Theory"` or `"Lab"` |
| `cc:hasPrerequisite` | Subject → Subject | A **direct** prerequisite |
| `cc:taughtBy` | Subject → Faculty | Who teaches it |
| `cc:develops` | Subject → Skill | A skill the subject builds |
| `cc:memberOf` | Faculty → Department | The faculty member's department |
| `cc:headedBy` | Department → Faculty | The Head of Department |
| `cc:designation`, `cc:email` | Faculty → text | Rank and contact address |
| `cc:requiresSkill` | CareerTrack → Skill | A skill the career needs |
| `cc:supports` | RemedialCourse → Subject | A subject the course helps with |
| `cc:coordinatedBy` | RemedialCourse → Faculty | Who runs the course |
| `cc:durationWeeks`, `cc:mode`, `cc:seatLimit` | RemedialCourse → value | Length, `"Weekend"`/`"Evening"`, capacity |

## The one idea that makes a graph worth having: property paths

Only **direct** prerequisites are stored:

```
subj:CS603  cc:hasPrerequisite  subj:CS503 .
subj:CS503  cc:hasPrerequisite  subj:CS401 , subj:CS404 .
subj:CS401  cc:hasPrerequisite  subj:CS301 , subj:CS303 .
```

"Everything CS603 depends on" is a walk along that edge for as long as it
continues. SPARQL writes the walk as a **property path** — a `+` after the
property means *one or more hops*:

```sparql
PREFIX cc:   <https://kg.cream-collar.com/campus/ontology#>
PREFIX subj: <https://kg.cream-collar.com/campus/subject/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?code ?name ?semester WHERE {
  subj:CS603 cc:hasPrerequisite+ ?p .
  ?p cc:code ?code ; rdfs:label ?name ; cc:semester ?semester .
}
ORDER BY ?semester ?code
```

In SQL the same question is a recursive common table expression. Here it is one
character. Other path operators you will meet:

| Path | Meaning |
|---|---|
| `a/b` | follow `a`, then `b` — e.g. `cc:offeredBy/cc:code` goes from a subject to its department's code |
| `a+` | one or more hops along `a` |
| `a*` | zero or more hops along `a` |
| `^a` | `a` walked backwards |

A triple pattern can have its variable on either side, so the reverse question
— *what depends on CS301?* — needs no new syntax:

```sparql
?s cc:hasPrerequisite+ subj:CS301 .
```

## Trying a query by hand

From a terminal in your workspace:

```bash
curl -s "$FUSEKI_URL/campus/sparql" \
  -H 'Accept: application/sparql-results+json' \
  --data-urlencode 'query=
    PREFIX cc: <https://kg.cream-collar.com/campus/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?code ?name WHERE { ?s a cc:Subject ; cc:code ?code ; rdfs:label ?name ; cc:semester 5 }
    ORDER BY ?code LIMIT 5'
```

The answer is JSON: `head.vars` lists the variables, `results.bindings` holds
one object per row. A variable that did not match in a row (inside `OPTIONAL`)
is simply **absent** from that row's object.

## What you cannot do, and why

- **Writes are refused.** The server exposes query endpoints only; an update
  request gets an HTTP error.
- **`SERVICE` is disabled.** That keyword asks the server to fetch data from
  another URL. On a shared server it would let anyone make the server send
  requests wherever they like, so it is switched off.
- **Slow queries are cancelled** after 30 seconds.
