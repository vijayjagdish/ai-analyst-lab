"""The SQL guard: decide whether a statement written by the model may run.

The agent turns a question into SQL. That SQL is text produced by a language
model from text typed by a stranger, and it is about to be sent to a database.
`validate_sql()` is the checkpoint in between.

It works on the PARSED statement, never on the raw string. A check such as
`"delete" not in sql.lower()` is wrong in both directions: it blocks a harmless
`WHERE status = 'deleted'` and it is walked around by a comment, a CTE or a
function call. A parser reads the statement the way the database will.

The guard is an ALLOW-list. It does not try to enumerate everything dangerous;
it states the small set of things an analyst's query needs and refuses the
rest:

    1. exactly one statement
    2. that statement is a query (SELECT, or a UNION/INTERSECT/EXCEPT of them)
    3. no node anywhere in it that writes, defines, locks or administers
    4. it reads only the three assignment tables (or its own CTEs)
    5. it calls no function the parser does not recognise as standard SQL
    6. it returns at most `max_rows` rows

This is one layer. services/dataset_service.run_readonly_query() adds a
read-only transaction and a time limit underneath it, on purpose: a guard that
is the ONLY thing between a model and your data will eventually be wrong.
"""

from __future__ import annotations

import logging

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

# sqlglot logs a warning each time it meets syntax it does not model ("falling
# back to parsing as a Command"). For us that IS the signal - we reject those -
# so the log line is noise in a notebook.
logging.getLogger("sqlglot").setLevel(logging.ERROR)

DIALECT = "postgres"
DEFAULT_MAX_ROWS = 200
MAX_SQL_LENGTH = 8000

ALLOWED_TABLES = frozenset({"student_performance", "subject_details", "department_details"})
ALLOWED_SCHEMAS = frozenset({"", "public"})

# Node types that must not appear ANYWHERE in the statement - not just at the
# top. PostgreSQL allows `WITH x AS (DELETE ... RETURNING *) SELECT * FROM x`:
# the statement starts with WITH, ends with SELECT, and deletes rows.
FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge,           # writes
    exp.Create, exp.Drop, exp.Alter, exp.TruncateTable,      # definitions
    exp.Command, exp.Copy, exp.Set, exp.Grant, exp.Use,      # administration
    exp.Transaction, exp.Commit, exp.Rollback, exp.Pragma,
    exp.Into,                                                # SELECT ... INTO makes a table
    exp.Lock,                                                # SELECT ... FOR UPDATE takes locks
)

# Functions sqlglot does not know by name arrive as exp.Anonymous. Unknown is
# refused by default - that is what stops pg_read_file(), pg_sleep(), dblink()
# and set_config() without listing them. These few are ordinary analytic
# functions it happens not to model.
EXTRA_FUNCTIONS = frozenset({"mode", "cume_dist", "percent_rank", "width_bucket",
                             "btrim", "concat_ws"})


class UnsafeSQLError(ValueError):
    """The statement was refused. The message says why, in words a model can act on."""


def validate_sql(sql: str, max_rows: int = DEFAULT_MAX_ROWS) -> str:
    """Check one SQL statement and return the version that is safe to execute.

    Args:
        sql: the statement to check.
        max_rows: the largest result the statement may return.

    Returns:
        The statement, re-generated from its parse tree, with a LIMIT of at
        most `max_rows`.

    Raises:
        UnsafeSQLError: the statement breaks one of the rules above.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise UnsafeSQLError("empty SQL statement")
    if len(sql) > MAX_SQL_LENGTH:
        raise UnsafeSQLError(f"SQL statement is longer than {MAX_SQL_LENGTH} characters")

    # >>> TODO M3-1 ─────────────────────────────────────────────────────────
    # Rules 1 and 2: parse, and insist on exactly one statement that is a query.
    # Leave the parsed statement in a variable called `tree`.
    #
    #   * sqlglot.parse(sql, read=DIALECT) returns a LIST - one entry per
    #     statement. Catch SqlglotError and raise UnsafeSQLError instead.
    #   * The list can contain None (an empty statement) and exp.Semicolon (a
    #     trailing comment after the final ';'). Drop both before counting, or
    #     `SELECT 1;` and `SELECT 1; -- done` look like two statements.
    #   * More than one statement left -> refuse. This is what stops
    #     `SELECT 1; DROP TABLE student_performance`.
    #   * A query in brackets parses as exp.Subquery; unwrap it (`tree.this`)
    #     until it is not one.
    #   * The statement must be an exp.Select or an exp.SetOperation (UNION,
    #     INTERSECT, EXCEPT). Anything else -> refuse.
    # >>> SOLUTION
    try:
        parsed = sqlglot.parse(sql, read=DIALECT)
    except SqlglotError as exc:
        raise UnsafeSQLError(f"could not parse the SQL: {str(exc).splitlines()[0]}") from exc

    statements = [s for s in parsed if s is not None and not isinstance(s, exp.Semicolon)]
    if not statements:
        raise UnsafeSQLError("empty SQL statement")
    if len(statements) > 1:
        raise UnsafeSQLError("only one SQL statement is allowed per call")

    tree = statements[0]
    while isinstance(tree, exp.Subquery) and tree.this is not None:
        tree = tree.this
    if not isinstance(tree, (exp.Select, exp.SetOperation)):
        raise UnsafeSQLError(
            f"only SELECT queries are allowed (this is a {type(tree).__name__.upper()} statement)")
    # <<< END TODO

    # >>> TODO M3-2 ─────────────────────────────────────────────────────────
    # Rules 3, 4 and 5: walk the whole tree.
    #
    #   Rule 3 - for node in tree.walk(): refuse if isinstance(node, FORBIDDEN_NODES).
    #
    #   Rule 4 - tables. First collect the names of the query's own CTEs:
    #                {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    #            Then for every exp.Table in the tree:
    #              * `table.this` being an exp.Func means a FUNCTION in the
    #                FROM clause (generate_series, dblink, pg_ls_dir) -> refuse.
    #              * `table.catalog` must be empty (no other databases).
    #              * `table.db` is the schema; it must be in ALLOWED_SCHEMAS.
    #                That alone refuses pg_catalog.* and information_schema.*.
    #              * the name must be a CTE of this query or in ALLOWED_TABLES.
    #            PostgreSQL folds unquoted names to lower case, so compare in
    #            lower case - but a QUOTED identifier keeps its case
    #            (`table.this.quoted`), and "Student_Performance" is not our
    #            table.
    #
    #   Rule 5 - functions. For every exp.Anonymous in the tree, refuse unless
    #            node.name.lower() is in EXTRA_FUNCTIONS.
    #
    # Say WHICH table or function was refused in the error message. The model
    # reads that message and usually fixes its own query on the next turn.
    # >>> SOLUTION
    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafeSQLError(
                f"{type(node).__name__.upper()} is not allowed - the database is read-only for the agent")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if isinstance(table.this, exp.Func):
            raise UnsafeSQLError("functions are not allowed in the FROM clause")
        if table.catalog:
            raise UnsafeSQLError(f"cross-database reference {table.catalog!r} is not allowed")
        schema = table.db.lower()
        if schema not in ALLOWED_SCHEMAS:
            raise UnsafeSQLError(f"schema {table.db!r} is not allowed")
        identifier = table.this
        quoted = bool(getattr(identifier, "quoted", False))
        name = table.name if quoted else table.name.lower()
        if not schema and name in cte_names:
            continue
        if name not in ALLOWED_TABLES:
            raise UnsafeSQLError(
                f"table {table.name!r} is not allowed; use only: " + ", ".join(sorted(ALLOWED_TABLES)))

    for func in tree.find_all(exp.Anonymous):
        if func.name.lower() not in EXTRA_FUNCTIONS:
            raise UnsafeSQLError(f"function {func.name}() is not allowed")
    # <<< END TODO

    # >>> TODO M3-2b ────────────────────────────────────────────────────────
    # Rule 6: the row limit, then return the SQL.
    #
    #   * tree.args.get("limit") is the top-level LIMIT (or FETCH FIRST) node,
    #     or None.
    #   * Keep it only when it is an exp.Limit whose expression is an integer
    #     literal no larger than max_rows. In every other case - no limit, a
    #     bigger number, LIMIT ALL, FETCH FIRST, an expression - replace it:
    #         tree.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))
    #   * Return tree.sql(dialect=DIALECT, comments=False). Generating the SQL
    #     from the tree, rather than returning the original string, means what
    #     runs is exactly what you inspected.
    # >>> SOLUTION
    limit = tree.args.get("limit")
    keep = False
    if isinstance(limit, exp.Limit):
        value = limit.expression
        if isinstance(value, exp.Literal) and not value.is_string:
            try:
                keep = 0 <= int(value.name) <= max_rows
            except ValueError:
                keep = False
    if not keep:
        tree.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))

    return tree.sql(dialect=DIALECT, comments=False)
    # <<< END TODO
