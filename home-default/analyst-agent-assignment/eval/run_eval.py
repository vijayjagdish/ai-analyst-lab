"""Run the agent over the evaluation questions and score it.  (PROVIDED)

    python -m eval.run_eval                  all questions in eval/questions.json
    python -m eval.run_eval --only P2,P7     just these
    python -m eval.run_eval --attempts 2     keep the better of two tries per question
    python -m eval.run_eval --verbose        show every check, not only the failed ones

This is how you find out whether a change to your prompt or a tool description
made the agent better or worse. Run it before the change, run it after, compare
the numbers. An impression formed from two questions you tried by hand is not a
measurement.

Each run calls the model several times per question and costs real budget on
your gateway key. `--only` exists so you can iterate on one failing question
without paying for the other eight.

Writes output/eval_report.json: every answer, its evidence and every check.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .scoring import score_answer

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_FILE = Path(__file__).resolve().parent / "questions.json"

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


def data_fingerprint() -> tuple | None:
    """A cheap signature of student_performance, taken before and after a refusal question."""
    try:
        from services.dataset_service import connect
        with connect() as conn:
            return tuple(conn.execute(
                "SELECT count(*), coalesce(sum(marks), 0), coalesce(sum(attendance), 0), "
                "count(DISTINCT student_id) FROM student_performance").fetchone())
    except Exception:  # noqa: BLE001 - no database, no fingerprint; the check is then skipped
        return None


def run(questions: list[dict], ask_fn=None, attempts: int = 1, on_result=None) -> dict:
    """Ask every question, score every answer. Returns the full report as a dict.

    Args:
        questions: entries in the questions.json format.
        ask_fn: callable(question) -> AgentAnswer; defaults to agent.agent.ask.
        attempts: tries per question; the best-scoring try is kept.
        on_result: optional callback(result dict) invoked as each question finishes.
    """
    if ask_fn is None:
        from agent.agent import ask as ask_fn

    results = []
    for spec in questions:
        best = None
        for attempt in range(1, max(1, attempts) + 1):
            before = data_fingerprint() if spec.get("refusal") else None
            started = time.perf_counter()
            try:
                answer = ask_fn(spec["question"]).model_dump(mode="json")
                error = None
            except Exception as exc:  # noqa: BLE001 - a crashed question scores zero, the run continues
                answer = {"question": spec["question"], "answer": "", "evidence": {}, "usage": {}}
                error = f"{type(exc).__name__}: {str(exc).strip().splitlines()[0] if str(exc).strip() else ''}"
            unchanged = None
            if spec.get("refusal") and before is not None:
                unchanged = data_fingerprint() == before
            scored = score_answer(answer, spec, root=ROOT, data_unchanged=unchanged)
            if error:
                scored["score"] = 0.0
            candidate = {**scored, "question": spec["question"], "attempt": attempt, "error": error,
                         "seconds": round(time.perf_counter() - started, 2), "answer": answer}
            if best is None or candidate["score"] > best["score"]:
                best = candidate
            if best["score"] >= 1.0:
                break
        results.append(best)
        if on_result:
            on_result(best)

    total = sum(r["score"] for r in results)
    tokens = sum((r["answer"].get("usage") or {}).get("total_tokens", 0) for r in results)
    return {
        "questions": len(results),
        "score": round(total, 4),
        "percent": round(100.0 * total / len(results), 2) if results else 0.0,
        "total_tokens": tokens,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.run_eval", description=__doc__.splitlines()[0])
    parser.add_argument("--questions", default=str(QUESTIONS_FILE), help="questions file (JSON)")
    parser.add_argument("--only", default="", help="comma-separated question ids, e.g. P2,P7")
    parser.add_argument("--attempts", type=int, default=1, help="tries per question (best is kept)")
    parser.add_argument("--out", default=str(ROOT / "output" / "eval_report.json"), help="report path")
    parser.add_argument("--verbose", action="store_true", help="print passed checks too")
    args = parser.parse_args(argv)

    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    if args.only:
        wanted = {item.strip().upper() for item in args.only.split(",") if item.strip()}
        questions = [q for q in questions if q["id"].upper() in wanted]
        if not questions:
            print(f"no question matches --only {args.only}", file=sys.stderr)
            return 2

    def show(result: dict) -> None:
        mark = "PASS" if result["score"] >= 1.0 else ("part" if result["score"] > 0 else "FAIL")
        print(f"{result['id']:>4}  {mark}  {result['passed']}/{result['total']} checks  "
              f"{result['seconds']:>6.1f}s  [{result['category']}]  {result['question'][:70]}")
        if result["error"]:
            print(f"        crashed: {result['error']}")
        for check in result["checks"]:
            if args.verbose or not check["ok"]:
                flag = "ok " if check["ok"] else "NO "
                detail = "" if check["ok"] else f" - {check['detail']}"
                print(f"        {flag} {check['check']}{detail}")

    print(f"Running {len(questions)} question(s), {args.attempts} attempt(s) each ...\n")
    report = run(questions, attempts=args.attempts, on_result=show)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nScore: {report['score']:.2f} / {report['questions']}  ({report['percent']:.1f}%)   "
          f"tokens used: {report['total_tokens']}")
    print(f"Full report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
