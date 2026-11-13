"""Command line for the assignment.  (PROVIDED)

    python -m agent.main --doctor            what is configured, and is each service reachable
    python -m agent.main --load-data         Milestone 1: CSV files -> your PostgreSQL database
    python -m agent.main --profile           Milestone 1: what the database now holds
    python -m agent.main --build-index       Milestone 4: policy documents -> your Qdrant collection
    python -m agent.main "your question"     ask the agent; writes output/report.md + results.json
    python -m agent.main --json "question"   the same, printing the full AgentAnswer as JSON

Run it from the assignment folder.
"""

from __future__ import annotations

import argparse
import json
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


def doctor() -> int:
    """Check each of the four outside services and say, in one line each, what is wrong."""
    from services import config

    print("Configuration (secrets masked):")
    for key, value in config.describe().items():
        print(f"  {key:18} {value}")
    settings = config.get_settings()
    failures = 0

    def check(label: str, probe) -> None:
        nonlocal failures
        try:
            print(f"  ok    {label}: {probe()}")
        except Exception as exc:  # noqa: BLE001 - this command exists to report any failure readably
            failures += 1
            first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
            print(f"  FAIL  {label}: {first[:200]}")

    def postgres() -> str:
        from services.dataset_service import connect
        with connect() as conn:
            user, database = conn.execute("SELECT current_user, current_database()").fetchone()
            tables = conn.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'").fetchone()[0]
        return f"connected as {user} to database {database} ({tables} table(s) in public)"

    def qdrant() -> str:
        from services.vector_client import get_client
        client = get_client()
        name = settings.qdrant_collection
        if not client.collection_exists(name):
            return f"reachable, but collection {name!r} does not exist yet"
        return f"collection {name!r} holds {client.count(name, exact=True).count} point(s)"

    def fuseki() -> str:
        import httpx
        settings.require("sparql_endpoint")
        response = httpx.post(settings.sparql_endpoint,
                              data={"query": "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }"},
                              headers={"Accept": "application/sparql-results+json"},
                              timeout=settings.http_timeout_s)
        response.raise_for_status()
        triples = response.json()["results"]["bindings"][0]["n"]["value"]
        return f"{settings.sparql_endpoint} answers, {triples} triples"

    def gateway() -> str:
        import httpx
        settings.require("gateway_url", "api_key")
        response = httpx.get(f"{settings.gateway_url}/models",
                             headers={"Authorization": f"Bearer {settings.api_key}"},
                             timeout=settings.http_timeout_s)
        response.raise_for_status()
        names = [m.get("id", "?") for m in response.json().get("data", [])]
        note = "" if not names or settings.model in names else f" - NOTE: {settings.model!r} is not in that list"
        return f"key accepted, {len(names)} model(s) available to it{note}"

    def embeddings() -> str:
        from services.vector_client import embed
        return f"{settings.embedding_model} loaded, {len(embed(['ping'])[0])} dimensions"

    print("\nServices:")
    check("PostgreSQL", postgres)
    check("Qdrant", qdrant)
    check("Jena Fuseki", fuseki)
    check("Bifrost gateway", gateway)
    check("Embedding model", embeddings)
    print("\nAll four services are reachable." if not failures
          else f"\n{failures} check(s) failed. Fix those before anything else - see TROUBLESHOOTING.md.")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent.main",
                                     description="CCIT analyst agent - assignment command line.")
    parser.add_argument("question", nargs="*", help="a question for the agent")
    parser.add_argument("--doctor", action="store_true", help="check configuration and connectivity")
    parser.add_argument("--load-data", action="store_true", help="load the CSV files into PostgreSQL")
    parser.add_argument("--profile", action="store_true", help="print the dataset profile")
    parser.add_argument("--build-index", action="store_true", help="index the policy documents in Qdrant")
    parser.add_argument("--json", action="store_true", help="print the full answer as JSON")
    args = parser.parse_args(argv)

    if args.doctor:
        return doctor()

    did_something = False
    if args.load_data:
        from services.dataset_service import load_dataset
        for table, count in load_dataset().items():
            print(f"  {table:22} {count:>6} rows")
        did_something = True
    if args.profile:
        from services.dataset_service import profile_dataset
        print(json.dumps(profile_dataset(), indent=2))
        did_something = True
    if args.build_index:
        from services.vector_client import build_index
        print(f"  indexed {build_index()} policy chunks")
        did_something = True

    question = " ".join(args.question).strip()
    if not question:
        if not did_something:
            parser.print_help()
        return 0

    from .agent import ask
    from .report import write_report

    answer = ask(question)
    paths = write_report(answer)
    if args.json:
        print(answer.model_dump_json(indent=2))
        return 0

    evidence = answer.evidence
    print(answer.answer)
    print("\n" + "-" * 72)
    print(f"rules retrieved : {', '.join(hit.rule_id for hit in evidence.policies) or 'none'}")
    print(f"sql statements  : " + (", ".join(run.status for run in evidence.sql) or "none"))
    print(f"graph lookups   : " + (", ".join(g.tool for g in evidence.graph) or "none"))
    print(f"charts          : " + (", ".join(c.path for c in evidence.charts) or "none"))
    print(f"run             : {answer.turns} turn(s), {answer.usage.get('total_tokens', 0)} tokens, "
          f"{answer.latency_s} s, model {answer.model}")
    print(f"report          : {paths['markdown']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
