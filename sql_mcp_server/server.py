"""
SQL MCP Server.

Exposes six tools for LLM agents to explore and query a Postgres database:

  list_tables()               -- overview of every table in the public schema
  describe_table(table)       -- columns, types, and foreign keys for one table
  search_schema(keyword)      -- find tables/columns whose name matches a keyword
  sample_rows(table, limit)   -- peek at a few real rows
  count_rows(table)           -- row count for a table
  execute_select(sql)         -- run an arbitrary read-only SELECT query

Run with:
    python -m sql_mcp_server.server

Or point Claude Desktop / any MCP client at it via stdio (see README.md).
"""
from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from . import security
from .config import settings
from .db import Database

db = Database(settings)
server = MCPServer(
    name="sql-explorer",
    title="SQL Database Explorer",
    description=(
        "Read-only tools for exploring and querying a Postgres database: "
        "list tables, inspect schema, search for columns, sample data, "
        "and run safe SELECT queries."
    ),
    version="0.1.0",
)


@server.tool()
def list_tables() -> list[dict[str, Any]]:
    """List every table in the public schema, with row-count-free metadata
    (name, description if set via COMMENT ON TABLE, on-disk size, and column
    count). Use this first to see what's available before querying.
    """
    return db.list_tables()


@server.tool()
def describe_table(table: str) -> dict[str, Any]:
    """Describe one table in detail: every column with its type and
    nullability, plus primary/foreign key constraints. Use this before
    writing a query against a table you haven't seen yet.
    """
    known = db.known_table_names()
    security.validate_identifier(table, known_names=known, kind="table")
    return {
        "table": table,
        "columns": db.describe_table_columns(table),
        "constraints": db.describe_table_constraints(table),
    }


@server.tool()
def search_schema(keyword: str) -> list[dict[str, Any]]:
    """Search all table and column names for a keyword. Useful when you
    know roughly what data you want (e.g. "email", "revenue") but don't
    know which table or column holds it.
    """
    return db.search_schema(keyword)


@server.tool()
def sample_rows(table: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return up to `limit` real rows from a table (default 5, capped at
    the server's max_rows setting) so you can see actual data shape and
    values before writing a query.
    """
    known = db.known_table_names()
    security.validate_identifier(table, known_names=known, kind="table")
    capped_limit = min(limit, settings.max_rows)
    return db.sample_rows(table, capped_limit)


@server.tool()
def count_rows(table: str) -> dict[str, Any]:
    """Return the total row count for a table."""
    known = db.known_table_names()
    security.validate_identifier(table, known_names=known, kind="table")
    return {"table": table, "row_count": db.count_rows(table)}


@server.tool()
def execute_select(sql: str) -> dict[str, Any]:
    """Execute a read-only SELECT (or WITH ... SELECT) query and return the
    result rows.

    Safety guarantees:
      - only a single SELECT/WITH statement is allowed (no ;-stacked
        statements, no comments, no INSERT/UPDATE/DELETE/DDL keywords)
      - the underlying DB connection uses a read-only Postgres role
      - a LIMIT is enforced server-side even if your query doesn't specify one
      - queries are subject to a statement timeout

    If a query is rejected, the error message explains why — fix the query
    and try again rather than attempting to work around the restriction.
    """
    try:
        validated = security.validate_select_query(
            sql, max_length=settings.max_query_length
        )
        limited = security.enforce_row_limit(validated, max_rows=settings.max_rows)
        rows = db.execute_select(limited)
        return {"row_count": len(rows), "rows": rows}
    except security.UnsafeQueryError as e:
        return {"error": str(e)}


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
