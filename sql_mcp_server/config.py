"""
Configuration loaded from environment variables.

The MCP server connects using a dedicated read-only Postgres role. This is a
deliberate defense-in-depth choice: even if the SQL-safety checks in
security.py had a bug, the database itself would refuse any write.

See README.md for how to create this role.

Values are read from the process environment. As a convenience for local
development, a `.env` file at the project root is loaded first (without
overriding variables already set in the real environment), so you don't have to
export PG* vars by hand every time.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader: KEY=VALUE lines, '#' comments, no dependency.

    Walks up from this file looking for a `.env` and applies any keys that
    aren't already present in os.environ (real env vars win).
    """
    for parent in Path(__file__).resolve().parents:
        env_path = parent / ".env"
        if env_path.is_file():
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
            return


_load_dotenv()


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
