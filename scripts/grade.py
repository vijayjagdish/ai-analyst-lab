#!/usr/bin/env python3
"""
grade.py - the AI Analyst Lab rubric, as code.           (TRAINER IMAGE ONLY)

    grade.py                              grade the assignment in the current tree
    grade.py path/to/analyst-agent-assignment
    grade.py --offline                    everything except the live-model part
    grade.py --batch DIR --rank           grade every submission under DIR, ranked
    grade.py --json                       one JSON object, for the platform
    grade.py --rubric                     print the weights and exit

What it does with a submission
------------------------------
1. Builds a clean GRADING COPY in a temporary folder:
     - the pristine starter (tests, data, policies, provided code) from the image
     - the student's ten code files laid over it
     - the hidden tests and hidden evaluation questions added
   The student's own copies of the tests, the scoring code and every file marked
   PROVIDED are never used. Editing a test to make it pass changes nothing here.
2. Runs the checkpoint + hidden tests there (no model involved; a scripted
   stand-in plays the model) and turns pass counts into marks per rubric area.
3. Unless --offline: runs the student's agent against the HIDDEN evaluation
   questions with the real model, twice per question, keeping the better try.
4. Reports marks per area, every failed check with its reason, and what a
   human still has to read.

What it does NOT do: judge REFLECTION.md, or whether an answer reads well. A
score here is evidence, not a verdict.

Where it must run, and with whose credentials
---------------------------------------------
The student's code is EXECUTED - against the PostgreSQL database, Qdrant
collection and gateway key in THIS process's environment. Their tables are
dropped and reloaded, their collection is cleared and rebuilt. So:

  * Run it in a workspace provisioned for grading (its own database and
    collection - `provision_student.py --student grader-1`), never in one that
    holds work you care about.
  * The gateway key's budget pays for step 3: roughly 10 hidden questions x up
    to 2 attempts per submission.
  * Submissions are graded one at a time; do not run two graders against the
    same database.

That is the same provisioning boundary sdv-ml-lab's grader has. The stronger
form - each submission in its own throwaway pod with its own credentials - is
the blueprint's "isolated Kubernetes Job" and is a later phase.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ASSIGNMENT_NAME = "analyst-agent-assignment"
PRISTINE = Path(os.environ.get("ANALYST_PRISTINE", f"/opt/assignment-default/{ASSIGNMENT_NAME}"))
HIDDEN = Path(os.environ.get("ANALYST_HIDDEN", "/opt/trainer-default/hidden"))

# The only files taken from a submission. Everything else is the image's copy.
STUDENT_FILES = [
    "services/llm_client.py", "services/dataset_service.py", "services/vector_client.py",
    "services/graph_client.py", "agent/sql_guard.py", "agent/tools.py", "agent/prompts.py",
    "agent/agent.py", "agent/charts.py", "agent/report.py",
]
# Provided modules a submission may NOT replace, even with a file of the same name.
PROTECTED = {"services/config.py", "services/__init__.py", "agent/evidence.py",
             "agent/main.py", "agent/__init__.py"}

# Weights from ASSIGNMENT.md. Keep these summing to 100.
WEIGHTS = {
    "data": 10, "sql_safety": 15, "sql_execution": 10, "retrieval": 15,
    "graph": 15, "agent": 10, "report": 5, "live": 20,
}
TITLES = {
    "data": "Data ingestion and profiling (M1)",
    "sql_safety": "SQL validation and safety (M3)",
    "sql_execution": "SQL execution (M3)",
    "retrieval": "Retrieval of business rules (M4)",
    "graph": "Knowledge graph (M5)",
    "agent": "Agent workflow (M6)",
    "report": "Charts and report (M7)",
    "live": "Live agent quality (M2, M8)",
}
LIVE_CHAT_MARKS = 2            # of the 20 "live" marks: Milestone 2's chat() tests
PASS_PCT = 60
PYTEST_TIMEOUT_S = 1200
EVAL_TIMEOUT_S = 3600

RESET, BOLD, GREEN, RED, YELLOW, DIM = (
    "\033[0m", "\033[1m", "\033[0;32m", "\033[0;31m", "\033[0;33m", "\033[2m")
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    RESET = BOLD = GREEN = RED = YELLOW = DIM = ""

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


# ── which rubric area a test belongs to ──────────────────────────────────────

def area_of(module: str, test: str) -> str | None:
    """Map a test (by module and name) to a rubric area. None = not credited."""
    module = module.rsplit(".", 1)[-1]
    if module in ("test_m1_data", "test_hidden_data"):
        return "data"
    if module in ("test_m3_sql", "test_hidden_sql"):
        guard = test.startswith(("test_guard", "test_hidden_guard", "test_refusal_message"))
        return "sql_safety" if guard else "sql_execution"
    if module in ("test_m4_policies", "test_hidden_policies"):
        return "retrieval"
    if module in ("test_m5_graph", "test_hidden_graph"):
        return "graph"
    if module in ("test_m6_agent", "test_hidden_agent"):
        return "agent"
    if module == "test_m7_report":
        return "report"
    return None          # test_environment (the platform), test_m2_llm (scored under "live")


# ── locating and assembling a submission ─────────────────────────────────────

def find_assignment(start: Path) -> Path | None:
    """The folder holding agent/ and services/, given it or one of its parents."""
    start = Path(start)
    for candidate in (start, start / ASSIGNMENT_NAME):
        if (candidate / "agent").is_dir() and (candidate / "services").is_dir():
            return candidate
    matches = sorted(p.parent for p in start.glob(f"*/{ASSIGNMENT_NAME}/agent") if p.is_dir())
    return matches[0] if matches else None


def build_grading_copy(submission: Path, target: Path) -> list[str]:
    """Assemble pristine starter + student code + hidden tests in `target`. Returns notes."""
    notes: list[str] = []
    shutil.copytree(PRISTINE, target, ignore=shutil.ignore_patterns(
        "__pycache__", ".pytest_cache", ".ipynb_checkpoints", ".env", "output"))
    (target / "output").mkdir(exist_ok=True)

    for relative in STUDENT_FILES:
        source = submission / relative
        if source.is_file():
            shutil.copy2(source, target / relative)
        else:
            notes.append(f"{relative} is missing from the submission - the unmodified starter file was used")

    # Helper modules the student added are welcome; replacing provided ones is not.
    for folder in ("agent", "services"):
        for source in sorted((submission / folder).glob("*.py")):
            relative = f"{folder}/{source.name}"
            if relative in PROTECTED:
                pristine = (PRISTINE / relative).read_bytes().replace(b"\r\n", b"\n")
                if source.read_bytes().replace(b"\r\n", b"\n") != pristine:
                    notes.append(f"{relative} is a PROVIDED file and was modified - the original was used instead")
            elif relative not in STUDENT_FILES:
                shutil.copy2(source, target / relative)
                notes.append(f"{relative} is an extra module added by the student (included)")

    for source in sorted((HIDDEN / "tests").glob("*.py")):
        shutil.copy2(source, target / "tests" / source.name)
    for name in ("expected_hidden.json", "questions_hidden.json"):
        shutil.copy2(HIDDEN / name, target / "tests" / name)
    return notes


def grader_env() -> dict:
    env = os.environ.copy()
    env["ANALYST_ENV_FILE"] = ""            # the grader's environment decides, not a .env file
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["NO_COLOR"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# ── running things ───────────────────────────────────────────────────────────

def preflight(workdir: Path) -> list[str]:
    """Problems with the GRADER's environment. Non-empty means: do not grade."""
    probe = (
        "import json, sys\n"
        "problems = []\n"
        "from services.config import get_settings\n"
        "s = get_settings()\n"
        "try:\n"
        "    from services.dataset_service import connect\n"
        "    with connect() as c: c.execute('SELECT 1')\n"
        "except Exception as e: problems.append('PostgreSQL: ' + str(e).strip().splitlines()[0])\n"
        "try:\n"
        "    from services.vector_client import get_client\n"
        "    assert get_client().collection_exists(s.qdrant_collection), 'collection does not exist'\n"
        "except Exception as e: problems.append('Qdrant: ' + (str(e).strip().splitlines() or ['?'])[0])\n"
        "try:\n"
        "    import httpx\n"
        "    r = httpx.post(s.sparql_endpoint, data={'query': 'ASK { ?s ?p ?o }'}, timeout=15)\n"
        "    r.raise_for_status()\n"
        "except Exception as e: problems.append('Fuseki: ' + (str(e).strip().splitlines() or ['?'])[0])\n"
        "print(json.dumps(problems))\n"
    )
    try:
        done = subprocess.run([sys.executable, "-c", probe], cwd=PRISTINE, env=grader_env(),
                              capture_output=True, text=True, timeout=120)
        return json.loads(done.stdout.strip().splitlines()[-1])
    except Exception as exc:  # noqa: BLE001
        return [f"could not run the environment probe: {exc}"]


def run_pytest(workdir: Path, expression: str, junit: Path) -> list[dict]:
    """Run pytest in the grading copy; return one record per test."""
    command = [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
               "-m", expression, f"--junitxml={junit}", "-o", "junit_family=xunit1"]
    try:
        subprocess.run(command, cwd=workdir, env=grader_env(), capture_output=True, text=True,
                       timeout=PYTEST_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return [{"module": "pytest", "name": "(run)", "ok": False,
                 "message": f"the test run did not finish within {PYTEST_TIMEOUT_S} s"}]
    if not junit.is_file():
        return [{"module": "pytest", "name": "(run)", "ok": False,
                 "message": "pytest produced no report - the submission probably fails at import"}]

    records = []
    for case in ET.parse(junit).getroot().iter("testcase"):
        problem = None
        for child in case:
            if child.tag in ("failure", "error"):
                problem = (child.get("message") or child.text or "failed").strip().splitlines()[0]
            elif child.tag == "skipped":
                problem = "skipped: " + (child.get("message") or "").strip().splitlines()[0]
        records.append({"module": case.get("classname", ""), "name": case.get("name", ""),
                        "ok": problem is None, "message": (problem or "")[:240]})
    return records


def run_live(workdir: Path, attempts: int) -> dict:
    """Milestone 2's tests and the hidden evaluation set, against the real model."""
    env = grader_env()
    chat = run_pytest(workdir, "live and not environment", workdir / "output" / "junit-live.xml")
    chat = [record for record in chat if record["module"].endswith("test_m2_llm")]

    # The agent needs the data loaded and the index built by the STUDENT's code.
    subprocess.run([sys.executable, "-m", "agent.main", "--load-data", "--build-index"],
                   cwd=workdir, env=env, capture_output=True, text=True, timeout=600)

    report_path = workdir / "output" / "eval_hidden.json"
    error = None
    try:
        done = subprocess.run(
            [sys.executable, "-m", "eval.run_eval", "--questions", "tests/questions_hidden.json",
             "--attempts", str(attempts), "--out", str(report_path)],
            cwd=workdir, env=env, capture_output=True, text=True, timeout=EVAL_TIMEOUT_S)
        if done.returncode != 0:
            error = (done.stderr.strip().splitlines() or ["evaluation run failed"])[-1][:240]
    except subprocess.TimeoutExpired:
        error = f"the evaluation run did not finish within {EVAL_TIMEOUT_S} s"

    evaluation = {"percent": 0.0, "results": [], "total_tokens": 0}
    if report_path.is_file():
        evaluation = json.loads(report_path.read_text(encoding="utf-8"))
    return {"chat": chat, "evaluation": evaluation, "error": error}


def reflection_status(submission: Path) -> tuple[int, int]:
    """(questions answered, questions asked) in REFLECTION.md - presence only, not quality."""
    path = submission / "REFLECTION.md"
    if not path.is_file():
        return 0, 5
    text = path.read_text(encoding="utf-8", errors="replace")
    sections = re.split(r"^## ", text, flags=re.M)[1:]
    answered = sum(1 for section in sections
                   if len(" ".join(re.findall(r"^>\s?(.*)$", section, flags=re.M)).split()) >= 12)
    return answered, len(sections) or 5


# ── grading one submission ───────────────────────────────────────────────────

def grade(submission: Path, offline: bool, attempts: int, keep: bool) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="analyst-grade-"))
    workdir = tmp / ASSIGNMENT_NAME
    try:
        notes = build_grading_copy(submission, workdir)
        records = run_pytest(workdir, "not live and not environment", workdir / "output" / "junit.xml")
        live = None
        if not offline:
            live = run_live(workdir, attempts)
    finally:
        if keep:
            print(f"{DIM}grading copy kept at {workdir}{RESET}", file=sys.stderr)
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    areas = {name: {"points": 0.0, "max": weight, "passed": 0, "total": 0}
             for name, weight in WEIGHTS.items()}
    failed: list[dict] = []
    for record in records:
        area = area_of(record["module"], record["name"])
        if area is None:
            if record["module"] == "pytest":            # the run itself broke
                failed.append({"area": "run", "check": record["name"], "reason": record["message"]})
            continue
        areas[area]["total"] += 1
        if record["ok"]:
            areas[area]["passed"] += 1
        else:
            failed.append({"area": area, "check": record["name"], "reason": record["message"]})
    for name, area in areas.items():
        if name != "live" and area["total"]:
            area["points"] = round(area["max"] * area["passed"] / area["total"], 2)

    live_summary = None
    if live is not None:
        chat_total = len(live["chat"]) or 2
        chat_passed = sum(1 for record in live["chat"] if record["ok"])
        evaluation = live["evaluation"]
        eval_marks = WEIGHTS["live"] - LIVE_CHAT_MARKS
        points = LIVE_CHAT_MARKS * chat_passed / chat_total + eval_marks * evaluation.get("percent", 0.0) / 100.0
        areas["live"].update({"points": round(points, 2), "passed": chat_passed, "total": chat_total})
        for record in live["chat"]:
            if not record["ok"]:
                failed.append({"area": "live", "check": record["name"], "reason": record["message"]})
        for result in evaluation.get("results", []):
            for check in result.get("checks", []):
                if not check["ok"]:
                    failed.append({"area": "live", "check": f"{result['id']}: {check['check']}",
                                   "reason": check.get("detail", "")})
        if live["error"]:
            failed.append({"area": "live", "check": "evaluation run", "reason": live["error"]})
        live_summary = {
            "eval_percent": evaluation.get("percent", 0.0),
            "questions": [{"id": r["id"], "score": r["score"], "category": r.get("category", "")}
                          for r in evaluation.get("results", [])],
            "total_tokens": evaluation.get("total_tokens", 0),
        }

    counted = [name for name in WEIGHTS if not (offline and name == "live")]
    points = round(sum(areas[name]["points"] for name in counted), 2)
    maximum = sum(WEIGHTS[name] for name in counted)
    percent = round(100.0 * points / maximum, 2) if maximum else 0.0

    answered, asked = reflection_status(submission)
    manual = [f"REFLECTION.md: {answered} of {asked} questions answered. Read them - the grader checks "
              "that an answer exists, never whether it shows understanding."]
    if offline:
        manual.append("Graded --offline: the 20 marks for live agent quality were NOT assessed. "
                      "The percentage is out of the remaining 80.")
    manual += notes

    return {
        "candidate": submission.parent.name if submission.name == ASSIGNMENT_NAME else submission.name,
        "submission": str(submission),
        "points": points, "max_points": maximum, "score_pct": percent,
        "pass_threshold": PASS_PCT, "verdict": "PASS" if percent >= PASS_PCT else "FAIL",
        "offline": offline,
        "areas": {name: areas[name] for name in counted},
        "live": live_summary,
        "failed_checks": failed,
        "manual_review": manual,
    }


# ── output ───────────────────────────────────────────────────────────────────

def print_report(result: dict) -> None:
    print(f"\n{BOLD}AI Analyst Lab - {result['candidate']}{RESET}  {DIM}{result['submission']}{RESET}")
    for name, area in result["areas"].items():
        detail = f"{area['passed']}/{area['total']} checks" if area["total"] else "no checks ran"
        if name == "live" and result["live"]:
            detail = (f"hidden evaluation {result['live']['eval_percent']:.1f}% · chat tests "
                      f"{area['passed']}/{area['total']} · {result['live']['total_tokens']} tokens")
        print(f"  {area['points']:>5.1f} / {area['max']:<3} {TITLES[name]:<36} {DIM}{detail}{RESET}")

    if result["failed_checks"]:
        print(f"\n{BOLD}Failed checks{RESET}")
        shown = 0
        for item in result["failed_checks"]:
            if shown == 40:
                print(f"  {DIM}... and {len(result['failed_checks']) - 40} more (use --json for all){RESET}")
                break
            print(f"  {RED}x{RESET} [{item['area']}] {item['check']}")
            if item["reason"]:
                print(f"      {YELLOW}{item['reason'][:200]}{RESET}")
            shown += 1

    print(f"\n{BOLD}Needs a human{RESET} {DIM}(not counted in the score){RESET}")
    for note in result["manual_review"]:
        print(f"  {YELLOW}·{RESET} {note}")

    colour = GREEN if result["verdict"] == "PASS" else RED
    print(f"\n{BOLD}Score: {result['points']:.1f} / {result['max_points']} = {result['score_pct']:.1f}% "
          f"({PASS_PCT}% to pass) - {colour}{result['verdict']}{RESET}\n")


def print_rubric() -> None:
    print(f"\n{BOLD}AI Analyst Lab - rubric{RESET} {DIM}(from ASSIGNMENT.md){RESET}\n")
    for name, weight in WEIGHTS.items():
        print(f"  {weight:>3}  {TITLES[name]}")
    print(f"\n  Pass mark: {BOLD}{PASS_PCT}%{RESET}. Within an area, marks are proportional to the checks passed")
    print("  (checkpoint tests + hidden tests). 'Live' = Milestone 2's chat tests "
          f"({LIVE_CHAT_MARKS}) + hidden evaluation questions ({WEIGHTS['live'] - LIVE_CHAT_MARKS}).")
    print(f"  {DIM}REFLECTION.md is reported for manual review and is not part of the score.{RESET}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Grade an AI Analyst Lab submission against its rubric.")
    parser.add_argument("submission", nargs="?", default=".",
                        help="the assignment folder, or a folder containing it (default: .)")
    parser.add_argument("--offline", action="store_true",
                        help="skip the live-model part; score out of 80")
    parser.add_argument("--attempts", type=int, default=2,
                        help="tries per hidden evaluation question (default 2; the best is kept)")
    parser.add_argument("--batch", metavar="DIR", help="grade every submission directory under DIR")
    parser.add_argument("--rank", action="store_true", help="with --batch: highest score first")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--keep", action="store_true", help="keep the temporary grading copy (for debugging)")
    parser.add_argument("--rubric", action="store_true", help="print the rubric and exit")
    args = parser.parse_args()

    if args.rubric:
        print_rubric()
        return 0

    for path, what in ((PRISTINE, "the pristine starter"), (HIDDEN / "tests", "the hidden tests")):
        if not path.is_dir():
            print(f"{RED}{what} was not found at {path}.{RESET} grade.py runs in the TRAINER image "
                  "(or set ANALYST_PRISTINE / ANALYST_HIDDEN).", file=sys.stderr)
            return 2

    problems = preflight(PRISTINE)
    if problems:
        print(f"{RED}This grading environment is not usable - nothing was graded:{RESET}", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print("Fix the grader's own service settings first; a student must not be marked down for them.",
              file=sys.stderr)
        return 2
    if not args.offline and not os.environ.get("OPENAI_API_KEY"):
        print(f"{RED}No gateway key in this environment (OPENAI_API_KEY).{RESET} "
              "Provide one, or grade with --offline.", file=sys.stderr)
        return 2

    if args.batch:
        root = Path(args.batch)
        if not root.is_dir():
            print(f"{RED}Not a directory: {root}{RESET}", file=sys.stderr)
            return 2
        results = []
        for entry in sorted(p for p in root.iterdir() if p.is_dir()):
            submission = find_assignment(entry)
            if submission is None:
                results.append({"candidate": entry.name, "score_pct": 0.0, "points": 0.0, "max_points": 0,
                                "verdict": "NO SUBMISSION", "manual_review": [], "failed_checks": []})
                continue
            print(f"{DIM}grading {entry.name} ...{RESET}", file=sys.stderr)
            result = grade(submission, args.offline, args.attempts, args.keep)
            result["candidate"] = entry.name
            results.append(result)
        if args.json:
            for result in results:
                print(json.dumps(result))
            return 0
        if args.rank:
            results.sort(key=lambda r: -r["score_pct"])
        print(f"\n{BOLD}{'candidate':<30}{'score':>8}  {'verdict':<14} failed checks{RESET}")
        print("-" * 70)
        for result in results:
            colour = GREEN if result["verdict"] == "PASS" else RED
            print(f"{result['candidate']:<30}{result['score_pct']:>7.1f}%  "
                  f"{colour}{result['verdict']:<14}{RESET} {len(result['failed_checks'])}")
        graded = [r for r in results if r["verdict"] != "NO SUBMISSION"]
        if graded:
            passed = sum(1 for r in graded if r["verdict"] == "PASS")
            mean = sum(r["score_pct"] for r in graded) / len(graded)
            print("-" * 70)
            print(f"{len(graded)} graded · {passed} passed · mean {mean:.1f}%\n")
        return 0

    submission = find_assignment(Path(args.submission))
    if submission is None:
        print(f"{RED}No assignment found under '{args.submission}'.{RESET} Pass the "
              f"{ASSIGNMENT_NAME} folder, or a folder that contains it.", file=sys.stderr)
        return 2
    result = grade(submission, args.offline, args.attempts, args.keep)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_report(result)
    # Exit 0 either way: this is a report, and a FAIL is a normal result.
    return 0


if __name__ == "__main__":
    sys.exit(main())
