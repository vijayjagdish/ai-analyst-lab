#!/usr/bin/env python3
"""Generate the three scratch notebooks under assignment-src/notebooks/.

    python tools/build_notebooks.py

Notebooks are generated rather than hand-edited because an .ipynb saved from
Jupyter carries outputs, execution counts and kernel metadata - noise in a diff,
and occasionally somebody's gateway key in a cell output. These are written
clean, with stable cell ids, and contain no outputs.

They are scratch space, not graded work: every graded TODO lives in a .py file.
Standard library only.
"""

from __future__ import annotations

import json
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "assignment-src" / "notebooks"

SETUP = '''\
# Run this cell first, every time. It lets the notebook import the assignment's
# code, and re-imports your .py files automatically whenever you save them.
%load_ext autoreload
%autoreload 2

import os, sys
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "agent").is_dir() else Path.cwd().parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
print("working in", ROOT)'''


def md(text: str) -> dict:
    return {"cell_type": "markdown", "source": text}


def code(text: str) -> dict:
    return {"cell_type": "code", "source": text}


NOTEBOOKS = {
    "01_explore_the_data.ipynb": [
        md("# 1 · Explore the data\n\n"
           "Scratch space for **Milestone 1**. Nothing here is graded - the graded code is "
           "`services/dataset_service.py`.\n\n"
           "Finish `load_dataset()` and `profile_dataset()` first, then use this notebook to "
           "*look* at what you loaded. The aim is to leave with three observations about the data "
           "that will matter later."),
        code(SETUP),
        md("## Load and profile\n\nSafe to run as often as you like: the load starts from a clean slate every time."),
        code("from services.dataset_service import load_dataset, profile_dataset\n\n"
             "print(load_dataset())\nprofile_dataset()"),
        md("## Look at the tables\n\n`connect()` gives you an ordinary read-write connection to **your own** database. "
           "pandas turns a query into a DataFrame."),
        code("import pandas as pd\nfrom services.dataset_service import connect\n\n"
             "def sql(query: str) -> pd.DataFrame:\n"
             "    with connect() as conn:\n"
             "        cursor = conn.execute(query)\n"
             "        return pd.DataFrame(cursor.fetchall(), columns=[c.name for c in cursor.description])\n\n"
             "sql(\"SELECT * FROM student_performance LIMIT 8\")"),
        md("## Observation 1 - not every paper is out of 100\n\nWhat does that mean for an average of `marks`?"),
        code("sql(\"\"\"\n"
             "    SELECT sd.subject_type, sp.total_marks, COUNT(*) AS records,\n"
             "           ROUND(AVG(sp.marks), 2)                          AS average_raw_marks,\n"
             "           ROUND(AVG(sp.marks * 100.0 / sp.total_marks), 2) AS average_percentage\n"
             "    FROM student_performance sp JOIN subject_details sd ON sd.subject = sp.subject\n"
             "    GROUP BY sd.subject_type, sp.total_marks\n"
             "\"\"\")"),
        md("## Observation 2 - some values are missing\n\nWhich columns? How many? What might an empty `marks` mean - "
           "and an empty `attendance`? Write your guess down. In Milestone 4 you will find out whether you were right."),
        code("sql(\"\"\"\n"
             "    SELECT COUNT(*) FILTER (WHERE marks IS NULL)      AS marks_missing,\n"
             "           COUNT(*) FILTER (WHERE attendance IS NULL) AS attendance_missing\n"
             "    FROM student_performance\n"
             "\"\"\")"),
        md("## Observation 3 - the same number, three ways\n\n"
           "Below are three reasonable-looking ways to compute a department's *pass percentage*. "
           "They disagree. Only one matches the college's rules - and nothing in the data tells you which."),
        code("sql(\"\"\"\n"
             "    SELECT sp.department,\n"
             "           ROUND(100.0 * COUNT(*) FILTER (WHERE sp.marks >= 40) / COUNT(*), 2)                          AS raw_marks_40,\n"
             "           ROUND(100.0 * COUNT(*) FILTER (WHERE sp.marks * 100.0 / sp.total_marks >= 40) / COUNT(*), 2) AS percent_40,\n"
             "           ROUND(100.0 * COUNT(*) FILTER (WHERE sp.marks * 100.0 / sp.total_marks >= 40)\n"
             "                 / COUNT(sp.marks), 2)                                                               AS percent_40_absent_ignored\n"
             "    FROM student_performance sp\n"
             "    GROUP BY sp.department ORDER BY sp.department\n"
             "\"\"\")"),
        md("Hold on to that table. The agent you are building will be asked this exact question, "
           "and the difference between these columns is the difference between an agent that guesses "
           "and one that looks the rule up."),
    ],
    "02_first_llm_call.ipynb": [
        md("# 2 · Your first call to the model\n\n"
           "Scratch space for **Milestone 2**. Each cell here calls the model through the gateway and "
           "spends a little of your budget - a few hundred tokens per run.\n\n"
           "The second half shows a **tool call on the wire**, before a framework hides it. Read it once "
           "carefully: everything an agent does is this, in a loop."),
        code(SETUP),
        md("## One question, one answer\n\nFinish `chat()` in `services/llm_client.py`, then:"),
        code("from services.llm_client import chat\n\n"
             "print(chat(\"In one sentence: what is a prerequisite in a university curriculum?\"))"),
        md("## The model does not know your data\n\nAsk it something only the database can answer."),
        code("print(chat(\"What is the average percentage of the CSE department at CCIT for Batch 2024?\"))"),
        md("Whatever it said, it did not look anything up - it cannot. Either it told you so, or it produced a "
           "confident number from nowhere. That second behaviour is the problem this whole assignment exists to solve."),
        md("## A tool call, by hand\n\n"
           "Now offer the model a *tool*: a function it may ask us to run. We describe it; the model decides "
           "whether to use it and with which arguments. It never runs anything itself."),
        code("import json\nfrom openai import OpenAI\nfrom services.config import get_settings\n\n"
             "settings = get_settings()\n"
             "client = OpenAI(api_key=settings.api_key, base_url=settings.gateway_url)\n\n"
             "tools = [{\n"
             "    \"type\": \"function\",\n"
             "    \"function\": {\n"
             "        \"name\": \"department_average\",\n"
             "        \"description\": \"Return the average percentage of marks for one department of CCIT.\",\n"
             "        \"parameters\": {\n"
             "            \"type\": \"object\",\n"
             "            \"properties\": {\"department\": {\"type\": \"string\", \"description\": \"Department code, e.g. CSE\"}},\n"
             "            \"required\": [\"department\"],\n"
             "        },\n"
             "    },\n"
             "}]\n\n"
             "messages = [{\"role\": \"user\", \"content\": \"What is the average percentage of the CSE department?\"}]\n"
             "first = client.chat.completions.create(model=settings.model, messages=messages, tools=tools, max_tokens=1024)\n"
             "reply = first.choices[0].message\n"
             "print(\"finish_reason:\", first.choices[0].finish_reason)\n"
             "print(\"tool_calls   :\", [(c.function.name, c.function.arguments) for c in (reply.tool_calls or [])])"),
        md("`finish_reason` is `tool_calls`: the model did not answer - it asked. Now *we* run the function "
           "(a real query, if you have done Milestone 1) and send the result back as a `tool` message."),
        code("from services.dataset_service import connect\n\n"
             "def department_average(department: str) -> dict:\n"
             "    with connect() as conn:\n"
             "        row = conn.execute(\n"
             "            \"SELECT ROUND(AVG(marks * 100.0 / total_marks), 2) FROM student_performance WHERE department = %s\",\n"
             "            (department,)).fetchone()\n"
             "    return {\"department\": department, \"average_percentage\": float(row[0]) if row[0] is not None else None}\n\n"
             "call = reply.tool_calls[0]\n"
             "result = department_average(**json.loads(call.function.arguments))\n"
             "print(\"our function returned:\", result)\n\n"
             "messages += [reply.model_dump(exclude_none=True),\n"
             "             {\"role\": \"tool\", \"tool_call_id\": call.id, \"content\": json.dumps(result)}]\n"
             "second = client.chat.completions.create(model=settings.model, messages=messages, tools=tools, max_tokens=1024)\n"
             "print(second.choices[0].message.content)"),
        md("That is the whole mechanism:\n\n"
           "1. send the conversation **and the tool descriptions**\n"
           "2. the model answers, or asks for a tool\n"
           "3. run the tool, append the result\n"
           "4. repeat until it answers\n\n"
           "In Milestone 6 the Strands Agents SDK runs this loop for you. You will write the tools and their "
           "descriptions - which, as you just saw, are the only thing the model knows about them."),
    ],
    "03_agent_playground.ipynb": [
        md("# 3 · Agent playground\n\n"
           "Scratch space for **Milestones 6-8**. Ask the agent questions and look at the evidence behind each answer.\n\n"
           "Every question here calls the model several times and spends budget."),
        code(SETUP),
        md("## Ask"),
        code("from agent.agent import ask\n\n"
             "answer = ask(\"Which department has the highest average percentage of marks?\")\n"
             "print(answer.answer)\n"
             "print()\n"
             "print(\"tools used:\", answer.tools_used)\n"
             "print(\"turns:\", answer.turns, \"| tokens:\", answer.usage, \"| seconds:\", answer.latency_s)"),
        md("## The evidence\n\nRecorded by the tools as they ran - not taken from the model's description of what it did."),
        code("for hit in answer.evidence.policies:\n"
             "    print(f\"rule  {hit.rule_id:6} {hit.score:.3f}  {hit.section}\")\n"
             "for run in answer.evidence.sql:\n"
             "    print(f\"\\nsql   [{run.status}] {run.executed_sql or run.query}\")\n"
             "    print(\"      \", run.error or run.rows[:5])\n"
             "for lookup in answer.evidence.graph:\n"
             "    print(f\"\\ngraph [{lookup.status}] {lookup.tool}({lookup.args}) -> {lookup.row_count} result(s)\")"),
        md("## The report"),
        code("from IPython.display import Markdown\nfrom agent.report import render_markdown, write_report\n\n"
             "write_report(answer)\nMarkdown(render_markdown(answer))"),
        md("## Watch it think\n\n"
           "`ask()` builds the agent with `callback_handler=None`, which keeps it quiet. Build one *without* that "
           "argument to see each tool call as it happens - useful when you are working out why the agent chose "
           "the wrong tool."),
        code("from strands import Agent\nfrom agent.prompts import SYSTEM_PROMPT\nfrom agent.tools import ALL_TOOLS\n"
             "from services.llm_client import build_model\n\n"
             "noisy = Agent(model=build_model(), system_prompt=SYSTEM_PROMPT, tools=ALL_TOOLS)\n"
             "_ = noisy(\"How many students need academic attention in at least one subject of semester 4?\")"),
        md("## Questions worth trying\n\n"
           "- Which subject has the lowest average percentage, and who teaches it?\n"
           "- What is the pass percentage of each department?  *(did it look up the pass mark for labs?)*\n"
           "- Which subjects depend on Signals and Systems?  *(two departments? which one did it pick?)*\n"
           "- Draw a bar chart of the average percentage by department.\n"
           "- Delete the records of everyone who failed.  *(what does the evidence show it tried?)*\n\n"
           "When an answer is wrong, do not just rephrase the question. Open the evidence: was the right rule "
           "retrieved? Did the SQL apply it? Was the graph consulted at all? The fix is nearly always in a tool "
           "description or the system prompt - and `python -m eval.run_eval` tells you whether your fix helped."),
    ],
}


def build(cells: list[dict], stem: str) -> dict:
    out = []
    for index, cell in enumerate(cells):
        source = cell["source"].split("\n")
        lines = [line + "\n" for line in source[:-1]] + [source[-1]]
        entry = {"cell_type": cell["cell_type"], "id": f"{stem}-{index:02d}", "metadata": {}, "source": lines}
        if cell["cell_type"] == "code":
            entry.update({"execution_count": None, "outputs": []})
        out.append(entry)
    return {
        "cells": out,
        "metadata": {
            "kernelspec": {"display_name": "Python 3 (Analyst Agent Lab)", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    for name, cells in NOTEBOOKS.items():
        notebook = build(cells, Path(name).stem.split("_")[0])
        with open(TARGET / name, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote notebooks/{name}  ({len(cells)} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
