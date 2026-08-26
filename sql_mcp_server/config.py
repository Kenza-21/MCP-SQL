"""
Configuration loaded from environment variables.

The MCP server connects using a dedicated read-only Postgres role. This is a
deliberate defense-in-depth choice: even if the SQL-safety checks in
security.py had a bug, the database itself would refuse any write.

See README.md for how to create this role.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str

    # Safety limits
    max_rows: int              # hard cap on rows returned by execute_select
    statement_timeout_ms: int  # Postgres-side query timeout
    max_query_length: int      # reject absurdly long query strings

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            pg_host=os.environ.get("PGHOST", "localhost"),
            pg_port=int(os.environ.get("PGPORT", "5432")),
            pg_db=os.environ.get("PGDATABASE", "sales"),
            pg_user=os.environ.get("PGUSER", "mcp_readonly"),
            pg_password=os.environ.get("PGPASSWORD", ""),
            max_rows=int(os.environ.get("MCP_MAX_ROWS", "500")),
            statement_timeout_ms=int(os.environ.get("MCP_STATEMENT_TIMEOUT_MS", "5000")),
            max_query_length=int(os.environ.get("MCP_MAX_QUERY_LENGTH", "4000")),
        )


settings = Settings.from_env()
