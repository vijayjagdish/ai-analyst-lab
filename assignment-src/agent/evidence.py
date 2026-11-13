"""The evidence trail.  (PROVIDED - read it; you will use it, not change it.)

An agent's answer is only as good as what it can show for it. This module is
where "show for it" is made concrete.

The rule the whole assignment is built on:

    EVIDENCE IS RECORDED BY THE TOOLS, NOT NARRATED BY THE MODEL.

When the model writes "I ran this query and got 68.47", that sentence is text
it generated - it may be true, a slip, or invented. When run_sql() executes a
query, IT writes down the SQL that actually ran and the rows that actually came
back. The report and the grader read this record, never the model's account of
what it did. A model cannot hallucinate its way into this log.

    EVIDENCE        the recorder the tools write to (one per process)
    AgentAnswer     what ask() returns: the answer text + the evidence behind it
"""

from __future__ import annotations

import threading
from typing import Any, Literal

from pydantic import BaseModel, Field

# Rows kept per query in the record. The model may see more (up to the SQL row
# limit); the record keeps enough to check the answer without the report
# becoming a data dump.
MAX_RECORDED_ROWS = 60


class PolicyHit(BaseModel):
    rule_id: str
    doc: str
    section: str
    score: float
    text: str
    query: str = Field(description="the search text that retrieved this passage")


class SqlRun(BaseModel):
    query: str = Field(description="the SQL exactly as the model wrote it")
    executed_sql: str | None = Field(default=None, description="what was sent to PostgreSQL after the guard")
    status: Literal["ok", "rejected", "error"]
    error: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False


class GraphLookup(BaseModel):
    tool: str
    args: dict[str, Any]
    status: Literal["ok", "error"]
    error: str | None = None
    row_count: int = 0
    result: Any = None


class ChartFile(BaseModel):
    path: str
    title: str
    kind: str
    points: int


class Evidence(BaseModel):
    policies: list[PolicyHit] = Field(default_factory=list)
    sql: list[SqlRun] = Field(default_factory=list)
    graph: list[GraphLookup] = Field(default_factory=list)
    charts: list[ChartFile] = Field(default_factory=list)


class AgentAnswer(BaseModel):
    question: str
    answer: str
    evidence: Evidence
    tools_used: list[str] = Field(default_factory=list, description="tool names in call order")
    model: str = ""
    stop_reason: str = ""
    turns: int = 0
    usage: dict[str, int] = Field(default_factory=dict)
    latency_s: float = 0.0


class EvidenceLog:
    """Collects what the tools did while one question is being answered.

    Strands runs tool functions on worker threads and may run several at once,
    so every method takes a lock. There is one log per process and ask() resets
    it at the start of each question: answer one question at a time.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._evidence = Evidence()
        self._tools: list[str] = []

    def reset(self) -> None:
        with self._lock:
            self._evidence = Evidence()
            self._tools = []

    def note_tool(self, name: str) -> None:
        with self._lock:
            self._tools.append(name)

    def add_policy_hits(self, query: str, hits: list[dict]) -> None:
        with self._lock:
            known = {hit.rule_id: hit for hit in self._evidence.policies}
            for hit in hits:
                existing = known.get(hit["rule_id"])
                if existing is None:
                    record = PolicyHit(query=query, **{k: hit[k] for k in
                                                      ("rule_id", "doc", "section", "score", "text")})
                    self._evidence.policies.append(record)
                    known[record.rule_id] = record
                elif hit["score"] > existing.score:
                    existing.score, existing.query = hit["score"], query

    def add_sql(self, query: str, status: str, executed_sql: str | None = None,
                error: str | None = None, columns: list[str] | None = None,
                rows: list[list] | None = None, row_count: int = 0,
                truncated: bool = False) -> None:
        rows = rows or []
        with self._lock:
            self._evidence.sql.append(SqlRun(
                query=query, executed_sql=executed_sql, status=status, error=error,
                columns=columns or [], rows=rows[:MAX_RECORDED_ROWS], row_count=row_count,
                truncated=truncated or len(rows) > MAX_RECORDED_ROWS,
            ))

    def add_graph(self, tool: str, args: dict, status: str, result: Any = None,
                  error: str | None = None) -> None:
        if isinstance(result, list):
            count = len(result)
        elif isinstance(result, dict):
            count = sum(len(v) for v in result.values() if isinstance(v, list)) or 1
        else:
            count = 0
        with self._lock:
            self._evidence.graph.append(GraphLookup(
                tool=tool, args=args, status=status, error=error, row_count=count, result=result))

    def add_chart(self, path: str, title: str, kind: str, points: int) -> None:
        with self._lock:
            self._evidence.charts.append(ChartFile(path=path, title=title, kind=kind, points=points))

    def snapshot(self) -> Evidence:
        with self._lock:
            return self._evidence.model_copy(deep=True)

    def tools_used(self) -> list[str]:
        with self._lock:
            return list(self._tools)


EVIDENCE = EvidenceLog()
