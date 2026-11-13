"""PostgreSQL: loading the dataset into YOUR database, profiling it, querying it.

Every student has their own database on the shared PostgreSQL server. You own
it: you can create tables in it and nobody else can connect to it. The
connection details arrive as the standard PG* environment variables, so
`psycopg.connect()` and `psql` both find it without being told where it is.

    load_dataset()        Milestone 1   CSV files  ->  three tables
    profile_dataset()     Milestone 1   what is actually in there
    run_readonly_query()  Milestone 3   execute a SELECT the agent wrote, safely

One rule runs through this whole file: SQL that came out of a language model is
UNTRUSTED INPUT. It gets a read-only transaction, a time limit and a row limit
no matter how carefully it was validated beforehand.
"""

from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg import sql

from .config import get_settings

# Parents before children: the foreign keys in sql/schema.sql make this order
# the only one that loads.
LOAD_ORDER = ("department_details", "subject_details", "student_performance")


def connect() -> psycopg.Connection:
    """Open a connection to your own database.  (PROVIDED)

    With an empty DATABASE_URL, libpq reads PGHOST, PGPORT, PGDATABASE, PGUSER
    and PGPASSWORD from the environment - the same variables `psql` uses.
    """
    settings = get_settings()
    return psycopg.connect(settings.database_url, connect_timeout=10,
                           application_name="analyst-agent")


def load_dataset(data_dir: Path | str | None = None) -> dict[str, int]:
    """Create the three tables and load the CSV files into them.

    Must be safe to run twice: the second run leaves exactly the same rows as
    the first, not double.

    Args:
        data_dir: folder holding the three CSV files; defaults to ./data.

    Returns:
        Row count per table, e.g. {"department_details": 5, ...}.
    """
    settings = get_settings()
    data_dir = Path(data_dir) if data_dir else settings.data_dir
    schema_sql = settings.schema_file.read_text(encoding="utf-8")

    # TODO M1-1 ─────────────────────────────────────────────────────────
    # Load data/<table>.csv into <table>, for each table in LOAD_ORDER.
    #
    #   1. Open a connection with connect(). Used as a context manager
    #      (`with connect() as conn:`) it COMMITS on a clean exit and rolls
    #      back if anything raises - so a half-finished load never persists.
    #   2. Execute schema_sql. It drops and recreates the tables, which is what
    #      makes the function repeatable.
    #   3. For each table, stream the CSV into PostgreSQL with COPY:
    #
    #        with cur.copy("COPY table (col1, col2, ...) FROM STDIN WITH (FORMAT csv)") as copy:
    #            copy.write(line)          # one CSV line at a time, header NOT included
    #
    #      Read the column list from the file's own header line so the load
    #      does not depend on column order.
    #   4. Count the rows of each table and return the counts.
    #
    # Why COPY and not INSERTs or pandas.to_sql: in CSV format an EMPTY field
    # is loaded as NULL, which is exactly what "absent" and "not recorded"
    # must become. A loader that turns them into 0, NaN or '' silently changes
    # every average you compute later.
    #
    # Build the statement with psycopg.sql.SQL / sql.Identifier rather than an
    # f-string. The names come from a file, and quoting identifiers properly is
    # a habit worth having before the day it matters.
    raise NotImplementedError("TODO M1-1 (services/dataset_service.py)")


def profile_dataset() -> dict:
    """Describe what is in `student_performance`, computed IN THE DATABASE.

    Returns a dict with exactly these keys:

        row_count            number of rows
        student_count        number of distinct students
        subject_count        number of distinct subjects
        department_count     number of distinct departments
        semesters            sorted list of semesters present, e.g. [3, 4]
        columns              column names in table order
        missing              {column name: number of NULLs}, for EVERY column
        total_marks_values   sorted list of distinct total_marks values
        mean_percentage      mean of marks * 100 / total_marks over rows that
                             have marks, rounded to 2 decimals (a float)
    """
    # TODO M1-2 ─────────────────────────────────────────────────────────
    # Query your database and build the dict described in the docstring.
    #
    #   * Column names: information_schema.columns, filtered on table_name and
    #     ordered by ordinal_position.
    #   * NULL counts for every column in ONE query:
    #         count(*) FILTER (WHERE some_column IS NULL)
    #     generated per column with sql.Identifier.
    #   * AVG() skips NULLs by itself - which is the behaviour the regulations
    #     ask for. Multiply by 100.0 (not 100) so the division is not integer
    #     division.
    #   * numeric columns come back from psycopg as Decimal. Convert with
    #     float() before returning, so the result can be turned into JSON.
    #
    # Compute this with SQL against your tables, not with pandas on the CSV.
    # The point of a profile is to prove what the DATABASE holds after loading.
    raise NotImplementedError("TODO M1-2 (services/dataset_service.py)")


def _jsonable(value):
    """Convert one database value into something json.dumps accepts.  (PROVIDED)"""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (_dt.date, _dt.datetime, _dt.time)):
        return value.isoformat()
    if isinstance(value, (bytes, memoryview)):
        return bytes(value).hex()
    return value


def run_readonly_query(query: str, max_rows: int | None = None,
                       timeout_ms: int | None = None) -> dict:
    """Execute one SELECT with three independent limits and return its rows.

    The query should already have passed agent.sql_guard.validate_sql(). This
    function does not trust that. It enforces, at the database:

        read-only     the transaction cannot write, whatever the SQL says
        time limit    statement_timeout cancels a runaway query
        row limit     at most `max_rows` rows are fetched and returned

    Args:
        query: a single SQL statement.
        max_rows: row cap; defaults to settings.sql_max_rows.
        timeout_ms: statement timeout; defaults to settings.sql_timeout_ms.

    Returns:
        {"columns": [...], "rows": [[...], ...], "row_count": int, "truncated": bool}
        `rows` holds JSON-safe values (floats, not Decimals).
        `truncated` is True when more rows existed than were returned.
    """
    settings = get_settings()
    max_rows = settings.sql_max_rows if max_rows is None else int(max_rows)
    timeout_ms = settings.sql_timeout_ms if timeout_ms is None else int(timeout_ms)

    # TODO M3-3 ─────────────────────────────────────────────────────────
    # Run `query` so that it CANNOT write, CANNOT run forever and CANNOT
    # return an unbounded result.
    #
    #   1. conn = connect(); set `conn.read_only = True` BEFORE executing
    #      anything. psycopg then opens the transaction as READ ONLY and
    #      PostgreSQL itself refuses INSERT/UPDATE/DELETE/DDL inside it.
    #   2. Inside the transaction: SET LOCAL statement_timeout = <timeout_ms>.
    #      (SET does not take bind parameters - format the integer in, after
    #      int() has made sure it IS an integer.)
    #   3. Execute the query. Column names are in cur.description.
    #   4. cur.fetchmany(max_rows + 1): fetching ONE extra row is how you learn
    #      whether the result was cut off without counting the whole thing.
    #   5. Always roll back and close - there is nothing to commit in a
    #      read-only transaction, and an open connection is a leaked one.
    #   6. Pass every value through _jsonable().
    #
    # Let database errors propagate. The tool wrapper in agent/tools.py turns
    # them into a message the model can read and act on.
    raise NotImplementedError("TODO M3-3 (services/dataset_service.py)")
