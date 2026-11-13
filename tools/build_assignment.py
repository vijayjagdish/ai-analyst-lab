#!/usr/bin/env python3
"""Generate the student starter from the reference solution.

    python tools/build_assignment.py            # rewrite home-default/analyst-agent-assignment/
    python tools/build_assignment.py --check    # fail if the committed starter is out of date

    assignment-src/                           the COMPLETE, WORKING assignment (trainer's copy)
    home-default/analyst-agent-assignment/    the same tree with the solutions removed (student's copy)

There is one source of truth - assignment-src/ - and the starter is derived from
it mechanically. That is what stops the two drifting apart: a hint, a function
signature or a provided helper cannot be fixed in one copy and forgotten in the
other, because there is no other. Never edit the starter by hand; edit
assignment-src/ and run this.

How a solution is marked in assignment-src
------------------------------------------
        # >>> TODO M3-1 ─────────────────────────────
        # Hints for the student. Kept in the starter.
        # >>> SOLUTION
        ...the reference code, removed from the starter...
        # <<< END TODO

In the starter the block becomes the hints followed by

        raise NotImplementedError("TODO M3-1 (agent/sql_guard.py)")

so an unfinished milestone fails with one line naming the TODO, not a stack of
confusing errors. Where a raise is the wrong placeholder (a module-level
constant, a decorated function that must exist to be imported) the block
supplies its own starter code, each line prefixed with `#|`:

        # >>> TODO M6-3 ─────────────────────────────
        # hints...
        # >>> STARTER
        #| SYSTEM_PROMPT = "You are a helpful assistant."
        # >>> SOLUTION
        SYSTEM_PROMPT = "...the real one..."
        # <<< END TODO

Standard library only.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
SOURCE = LAB_ROOT / "assignment-src"
TARGET = LAB_ROOT / "home-default" / "analyst-agent-assignment"

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ipynb_checkpoints"}
SKIP_FILES = {".env"}
# output/ is where a student's own results go. Ship the folder, not the trainer's leftovers.
KEEP_ONLY_PLACEHOLDER_IN = {"output"}

TODO_OPEN = re.compile(r"^(?P<indent>\s*)# >>> TODO (?P<id>[A-Za-z0-9-]+)(?P<rest>.*)$")
STARTER_MARK = re.compile(r"^\s*# >>> STARTER\s*$")
SOLUTION_MARK = re.compile(r"^\s*# >>> SOLUTION\s*$")
TODO_CLOSE = re.compile(r"^\s*# <<< END TODO\s*$")


class MarkerError(Exception):
    pass


def strip_solutions(text: str, relative_path: str) -> tuple[str, list[str]]:
    """Return (starter text, ids of the TODO blocks found)."""
    out: list[str] = []
    ids: list[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        match = TODO_OPEN.match(lines[i])
        if not match:
            if STARTER_MARK.match(lines[i]) or SOLUTION_MARK.match(lines[i]) or TODO_CLOSE.match(lines[i]):
                raise MarkerError(f"{relative_path}:{i + 1}: marker outside a TODO block")
            out.append(lines[i])
            i += 1
            continue

        indent, todo_id = match.group("indent"), match.group("id")
        opened_at = i + 1
        ids.append(todo_id)
        out.append(f"{indent}# TODO {todo_id}{match.group('rest')}")
        i += 1

        starter: list[str] | None = None
        state = "hints"
        while True:
            if i >= len(lines):
                raise MarkerError(f"{relative_path}:{opened_at}: TODO {todo_id} is never closed")
            line = lines[i]
            if TODO_OPEN.match(line):
                raise MarkerError(f"{relative_path}:{i + 1}: TODO opened inside TODO {todo_id}")
            if TODO_CLOSE.match(line):
                if state == "hints":
                    raise MarkerError(f"{relative_path}:{opened_at}: TODO {todo_id} has no '# >>> SOLUTION'")
                i += 1
                break
            if STARTER_MARK.match(line):
                if state != "hints":
                    raise MarkerError(f"{relative_path}:{i + 1}: '# >>> STARTER' must come before the solution")
                state, starter = "starter", []
            elif SOLUTION_MARK.match(line):
                state = "solution"
            elif state == "hints":
                out.append(line)
            elif state == "starter":
                stripped = line.lstrip()
                if not stripped.startswith("#|"):
                    raise MarkerError(f"{relative_path}:{i + 1}: starter lines must begin with '#|'")
                body = stripped[2:]
                body = body[1:] if body.startswith(" ") else body
                lead = line[: len(line) - len(stripped)]
                starter.append((lead + body).rstrip())
            # state == "solution": the line is dropped
            i += 1

        if starter is None:
            out.append(f'{indent}raise NotImplementedError("TODO {todo_id} ({relative_path})")')
        else:
            out.extend(starter)
    return "\n".join(out), ids


def planned_files() -> dict[Path, bytes]:
    """Every file of the starter, keyed by path relative to TARGET."""
    files: dict[Path, bytes] = {}
    todo_ids: dict[str, str] = {}
    for path in sorted(SOURCE.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(SOURCE)
        if any(part in SKIP_DIRS for part in relative.parts) or relative.name in SKIP_FILES:
            continue
        if relative.parts[0] in KEEP_ONLY_PLACEHOLDER_IN and relative.name != ".gitkeep":
            continue
        raw = path.read_bytes()
        if path.suffix == ".py":
            text = raw.decode("utf-8").replace("\r\n", "\n")
            starter, ids = strip_solutions(text, relative.as_posix())
            for todo_id in ids:
                if todo_id in todo_ids:
                    raise MarkerError(f"TODO id {todo_id} is used in both {todo_ids[todo_id]} and {relative}")
                todo_ids[todo_id] = relative.as_posix()
            try:
                compile(starter, str(relative), "exec")
            except SyntaxError as exc:
                raise MarkerError(f"the starter for {relative} does not compile: {exc}") from exc
            raw = starter.encode("utf-8")
        elif path.suffix in {".md", ".sh", ".txt", ".json", ".csv", ".sql", ".ini", ".ipynb", ".template", ".ttl"} \
                or relative.name in {".env.template", ".gitignore"}:
            raw = raw.replace(b"\r\n", b"\n")       # one line-ending convention inside the image
        files[relative] = raw
    if not todo_ids:
        raise MarkerError("no TODO blocks found - is assignment-src/ the marked-up solution?")
    planned_files.todo_ids = todo_ids            # type: ignore[attr-defined]
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="do not write; exit 1 if home-default/ differs from what would be generated")
    args = parser.parse_args()

    try:
        files = planned_files()
    except MarkerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    todo_ids = planned_files.todo_ids            # type: ignore[attr-defined]

    if args.check:
        problems = []
        existing = {p.relative_to(TARGET) for p in TARGET.rglob("*")
                    if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(TARGET).parts)} \
            if TARGET.is_dir() else set()
        for relative, data in files.items():
            target = TARGET / relative
            if not target.is_file():
                problems.append(f"missing: {relative.as_posix()}")
            elif target.read_bytes().replace(b"\r\n", b"\n") != data.replace(b"\r\n", b"\n"):
                problems.append(f"stale:   {relative.as_posix()}")
        problems += [f"extra:   {relative.as_posix()}" for relative in sorted(existing - set(files))]
        for line in problems:
            print(line, file=sys.stderr)
        print("starter is up to date" if not problems else
              f"{len(problems)} difference(s) - run: python tools/build_assignment.py")
        return 1 if problems else 0

    if TARGET.exists():
        shutil.rmtree(TARGET)
    for relative, data in files.items():
        target = TARGET / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    print(f"wrote {len(files)} files to {TARGET.relative_to(LAB_ROOT).as_posix()}/")
    by_file: dict[str, list[str]] = {}
    for todo_id, where in todo_ids.items():
        by_file.setdefault(where, []).append(todo_id)
    print(f"{len(todo_ids)} TODO blocks for the student:")
    for where in sorted(by_file):
        print(f"  {where:34} {', '.join(by_file[where])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
