#!/usr/bin/env python3
"""Check the answer key against a real database.

    python trainer/verify_answer_key.py              # uses the PG* environment variables
    python trainer/verify_answer_key.py --load       # load the CSV files first

The answer key's figures were computed in plain Python from the CSV files
(tools/build_answer_key.py). Each evaluation question also carries a reference
SQL statement. This script runs every reference statement on PostgreSQL and
checks that the figures the key expects appear in what the database returns.

Run it after regenerating the dataset or editing a policy rule. If the two
disagree, one of three things is wrong - the Python implementation of a rule,
the reference SQL, or the wording of the rule that both were written from -
and it must be settled BEFORE students are graded against the key.

It only reads (SELECT), unless --load is given, which recreates the three
assignment tables in whatever database PG* points at.

Needs psycopg; run it in the lab image or any environment that has it.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
KEY_FILE = LAB_ROOT / "trainer" / "answer-key.json"
SOURCE = LAB_ROOT / "assignment-src"


def numbers(rows) -> list[float]:
    found = []
    for row in rows:
        for cell in row:
            if isinstance(cell, bool):
                continue
            if isinstance(cell, (int, float, Decimal)):
                found.append(float(cell))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--load", action="store_true",
                        help="(re)create the tables from assignment-src/data before checking")
    args = parser.parse_args()

    import psycopg

    key = json.loads(KEY_FILE.read_text(encoding="utf-8"))
    if args.load:
        sys.path.insert(0, str(SOURCE))
        from services.dataset_service import load_dataset
        print("loaded:", load_dataset(SOURCE / "data"))

    problems = 0
    with psycopg.connect("", connect_timeout=10) as conn:
        conn.read_only = True
        for question in key["public"] + key["hidden"]:
            sql = question.get("reference_sql")
            if not sql:
                continue
            rows = conn.execute(sql).fetchall()
            # A question that asks "how many" may be answered by a query that
            # LISTS the rows; the count is then the number of rows returned.
            got = numbers(rows) + [float(len(rows))]
            text = json.dumps(rows, default=str)
            targets = question.get("answer_numbers", []) + question.get("evidence_numbers", [])
            misses = [t for t in targets
                      if not any(abs(value - float(t["value"])) <= max(0.011, float(t.get("tolerance", 0)) / 5)
                                 for value in got)]
            # Names the key expects in the answer and that SQL alone can supply.
            for group in question.get("answer_includes", []):
                if question.get("refusal") or question.get("graph_includes"):
                    continue
                if any(str(item) in text for item in group):
                    continue
                if any(len(str(item)) <= 6 and str(item).isupper() for item in group):
                    misses.append({"value": " / ".join(map(str, group)), "what": "expected in the result"})
            status = "ok      " if not misses else "MISMATCH"
            print(f"{status} {question['id']:>4}  {len(rows)} row(s)  "
                  f"expects {[t['value'] for t in targets] or '-'}")
            for miss in misses:
                problems += 1
                print(f"           not found in the SQL result: {miss['value']} ({miss.get('what', '')})")
                print(f"           the query returned: {text[:300]}")
    print("\nThe answer key and the reference SQL agree." if not problems
          else f"\n{problems} disagreement(s) between the answer key and the reference SQL.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
