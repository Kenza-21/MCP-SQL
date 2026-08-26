"""
All defenses that keep this MCP server read-only and injection-safe.

Two different problems are handled here, and they need different techniques:

1. Identifiers (table/column names) can't be parameterized with placeholders
   in SQL (psycopg2 %s only binds values, not identifiers). So identifiers are
   validated against an allow-list fetched live from the database, plus a
   strict regex.

2. Freeform SQL from `execute_select` can't be allow-listed. It's validated
   structurally: must be a single statement, must start with SELECT or WITH,
   and must not contain any data-modifying or admin keywords.

Defense in depth: even if every check here had a bug, the DB connection
itself uses a read-only Postgres role (see config.py / README), and every
query runs inside a session with `SET TRANSACTION READ ONLY` and a
statement_timeout.
"""
from __future__ import annotations

import re

IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Keywords that should never appear in a query this server executes.
# Matched as whole words, case-insensitive.
FORBIDDEN_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "grant", "revoke", "copy", "vacuum", "reindex", "cluster", "execute",
    "call", "do", "comment", "lock", "listen", "notify", "refresh",
    "merge", "into",  # blocks "SELECT ... INTO new_table"
]

FORBIDDEN_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(FORBIDDEN_KEYWORDS) + r")\b", re.IGNORECASE
)

ALLOWED_START_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


class UnsafeQueryError(ValueError):
    """Raised when a query or identifier fails a safety check."""


def validate_identifier(name: str, *, known_names: set[str], kind: str = "identifier") -> str:
    """Validate a table or column name against a strict pattern AND a live
    allow-list fetched from the database. Raises UnsafeQueryError if invalid.
    """
    if not IDENTIFIER_RE.match(name):
        raise UnsafeQueryError(
            f"Invalid {kind} '{name}': must match ^[a-zA-Z_][a-zA-Z0-9_]*$"
        )
    if name not in known_names:
        raise UnsafeQueryError(
            f"Unknown {kind} '{name}': not found in the current database schema"
        )
    return name


def validate_select_query(sql: str, *, max_length: int) -> str:
    """Validate a freeform SQL string intended for execute_select.

    Raises UnsafeQueryError on anything that isn't a single, plain read
    query. Returns the (stripped) query on success.
    """
    if not sql or not sql.strip():
        raise UnsafeQueryError("Query is empty")

    if len(sql) > max_length:
        raise UnsafeQueryError(f"Query exceeds max length of {max_length} characters")

    stripped = sql.strip()

    # Reject stacked/multiple statements. A single trailing semicolon is
    # tolerated and stripped; anything else containing a semicolon is
    # rejected outright (covers "SELECT 1; DROP TABLE users;").
    body = stripped[:-1] if stripped.endswith(";") else stripped
    if ";" in body:
        raise UnsafeQueryError("Multiple statements are not allowed")

    if not ALLOWED_START_RE.match(body):
        raise UnsafeQueryError("Only SELECT / WITH ... SELECT queries are allowed")

    # Block SQL comments, which can be used to smuggle statements past
    # naive filters (e.g. "SELECT 1; -- DROP" or /* */ tricks).
    if "--" in body or "/*" in body or "*/" in body:
        raise UnsafeQueryError("SQL comments are not allowed in queries")

    match = FORBIDDEN_KEYWORD_RE.search(body)
    if match:
        raise UnsafeQueryError(f"Forbidden keyword '{match.group(0)}' in query")

    return body


def enforce_row_limit(sql: str, *, max_rows: int) -> str:
    """Append a LIMIT clause if the query doesn't already have one, or the
    existing limit exceeds max_rows. Simple heuristic, not a full SQL parser
    by design — this is a belt-and-braces cap, not the primary safety
    mechanism (the primary mechanism is read-only role + validation above).
    """
    limit_match = re.search(r"\blimit\s+(\d+)\b", sql, re.IGNORECASE)
    if limit_match:
        existing = int(limit_match.group(1))
        if existing <= max_rows:
            return sql
        return re.sub(
            r"\blimit\s+\d+\b", f"LIMIT {max_rows}", sql, flags=re.IGNORECASE
        )
    return f"{sql}\nLIMIT {max_rows}"
