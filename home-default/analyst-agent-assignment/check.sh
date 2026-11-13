#!/bin/bash
# Run a milestone's checkpoint tests.
#
#     ./check.sh env        the container and the four services (should always pass)
#     ./check.sh 3          milestone 3
#     ./check.sh all        every milestone, summarised
#     ./check.sh 8          the evaluation run (calls the model - costs budget)
#     ./check.sh submit     run everything, then pack output/submission.zip
#
# Milestone tests are RED until you do the milestone. That is the design - a
# checkpoint that passes before you write anything is not a checkpoint.

set -uo pipefail
cd "$(dirname "$0")"

GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
if [ ! -t 1 ] || [ -n "${NO_COLOR:-}" ]; then GREEN=""; RED=""; DIM=""; RESET=""; fi

declare -A FILE=(
    [1]=tests/test_m1_data.py      [2]=tests/test_m2_llm.py
    [3]=tests/test_m3_sql.py       [4]=tests/test_m4_policies.py
    [5]=tests/test_m5_graph.py     [6]=tests/test_m6_agent.py
    [7]=tests/test_m7_report.py
)
declare -A TITLE=(
    [1]="Load and profile the data"   [2]="Talk to the model (live)"
    [3]="Safe SQL"                    [4]="Retrieve the rules"
    [5]="Query the knowledge graph"   [6]="Assemble the agent"
    [7]="Charts and the report"
)

usage() {
    echo "usage: ./check.sh <env|1-8|all|submit>"
    echo "   e.g. ./check.sh 3"
    exit 1
}

run_all() {   # prints the summary; returns 0 only if every milestone passes
    local pass=0 fail=0 n
    for n in 1 2 3 4 5 6 7; do
        if python -m pytest "${FILE[$n]}" -q --no-header >/dev/null 2>&1; then
            printf '  %sM%s  PASS%s  %s\n' "$GREEN" "$n" "$RESET" "${TITLE[$n]}"; pass=$((pass+1))
        else
            printf '  %sM%s  ----%s  %s\n' "$DIM" "$n" "$RESET" "${TITLE[$n]}"; fail=$((fail+1))
        fi
    done
    echo ""
    echo "  ${pass} of 7 checkpoints pass.  Milestone 8 is the evaluation run: ./check.sh 8"
    [ "$fail" -eq 0 ]
}

[ $# -eq 1 ] || usage

case "$1" in
    env|environment)
        echo "Checking the container and the four services. This should pass from"
        echo "day one - a failure here is not your code."
        echo ""
        exec python -m pytest tests/test_environment.py -v --no-header
        ;;
    all)
        run_all
        exit $?
        ;;
    8|eval)
        echo "Running the evaluation set against the live model (this spends budget)."
        echo ""
        exec python -m eval.run_eval
        ;;
    submit)
        run_all || echo "  (you can still submit - unfinished milestones simply score nothing)"
        echo ""
        if ! grep -qE '^> .{20,}' REFLECTION.md 2>/dev/null; then
            printf '%sREFLECTION.md still has no answers.%s Fill it in, then run this again.\n' "$RED" "$RESET"
            exit 1
        fi
        python - <<'PY'
import zipfile
from pathlib import Path

root = Path(".")
keep_dirs = ("agent", "services")
keep_files = ("REFLECTION.md", "output/eval_report.json", "output/report.md", "output/results.json")
target = root / "output" / "submission.zip"
target.parent.mkdir(exist_ok=True)
names = []
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
    for folder in keep_dirs:
        for path in sorted((root / folder).rglob("*.py")):
            archive.write(path, path.as_posix()); names.append(path.as_posix())
    for name in keep_files:
        if (root / name).is_file():
            archive.write(root / name, name); names.append(name)
    for path in sorted((root / "output" / "charts").glob("*.png")):
        archive.write(path, path.as_posix()); names.append(path.as_posix())
print(f"  packed {len(names)} files into {target.as_posix()}")
for name in names:
    print(f"    {name}")
if "output/eval_report.json" not in names:
    print("\n  note: no evaluation report yet - run ./check.sh 8 first so your result is included.")
PY
        exit $?
        ;;
    [1-7])
        ;;
    *)
        usage
        ;;
esac

N="$1"
printf '%sMilestone %s - %s%s\n\n' "$DIM" "$N" "${TITLE[$N]}" "$RESET"

# -x stops at the first failure: the tests are ordered so the first one to fail
# is usually the one worth reading, and twenty red tracebacks are not more
# informative than one.
python -m pytest "${FILE[$N]}" -v --no-header -x
STATUS=$?

echo ""
if [ "$STATUS" -eq 0 ]; then
    printf '%sMilestone %s checkpoint passed.%s\n' "$GREEN" "$N" "$RESET"
else
    printf '%sNot yet.%s Read the failure above - the messages are written to tell you\n' "$RED" "$RESET"
    printf 'what is wrong, not just that something is.\n'
fi
exit "$STATUS"
