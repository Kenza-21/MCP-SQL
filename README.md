# SQL MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that exposes
a Postgres database to LLM agents (Claude Desktop, Claude Code, or any MCP
client) through six read-only tools. Point an agent at it and ask questions
like *"which customers placed more than five orders last month?"* — the agent
explores the schema and queries the data itself, through the tools below.

## Tools

| Tool | Description |
|---|---|
| `list_tables()` | Overview of every table: name, description, size, column count |
| `describe_table(table)` | Columns, types, and foreign key relationships for one table |
| `search_schema(keyword)` | Find tables/columns whose name matches a keyword |
| `sample_rows(table, limit)` | Peek at real rows (default 5) |
| `count_rows(table)` | Row count for a table |
| `execute_select(sql)` | Run an arbitrary read-only `SELECT` / `WITH ... SELECT` query |

## Why this isn't "just a wrapper around psycopg2"

Text-to-SQL demos are common; the part that's actually hard — and where this
project puts its effort — is making `execute_select` safe to hand to an LLM
that will generate arbitrary SQL:

1. **Read-only Postgres role.** The server connects as `mcp_readonly`, a role
   with `SELECT`-only grants (see `scripts/init_schema.sql`). Even a bug in
   the application-level checks below can't cause a write.
2. **Session-level read-only enforcement.** Every connection runs
   `SET TRANSACTION READ ONLY` (`db.py`).
3. **Statement validation** (`security.py`): only a single `SELECT`/`WITH`
   statement is allowed — no stacked statements (`; DROP TABLE ...`), no SQL
   comments (blocks comment-based statement smuggling), and a keyword
   blocklist covers `INSERT`/`UPDATE`/`DELETE`/`DDL`/`GRANT`/etc., including
   `SELECT ... INTO` (which silently creates a table).
4. **Identifier validation.** `describe_table`, `sample_rows`, and
   `count_rows` take a table name as a parameter. Since SQL identifiers can't
   be parameterized with placeholders, table names are checked against a
   strict regex *and* a live allow-list fetched from
   `information_schema` — not just string-escaped.
5. **Resource limits.** A Postgres `statement_timeout` prevents runaway
   queries, and a server-side row cap is enforced on every query result,
   even if the LLM's query didn't specify a `LIMIT`.

## Quickstart

```bash
git clone <this-repo>
cd sql-mcp-server
pip install -r requirements.txt

# 1. Start Postgres with the sample schema
docker compose up -d

# 2. Generate sample e-commerce data (uses the postgres superuser, not mcp_readonly)
PGUSER=postgres PGPASSWORD=postgres python scripts/generate_sample_data.py

# 3. Configure the server to use the read-only role
cp .env.example .env
# edit .env if you changed the default mcp_readonly password

# 4. Run the tests
pytest

# 5. Run the server (stdio transport, for use with an MCP client)
python -m sql_mcp_server.server
```

## Connecting to Claude Desktop

Add to your Claude Desktop MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "sql-explorer": {
      "command": "python",
      "args": ["-m", "sql_mcp_server.server"],
      "cwd": "/absolute/path/to/sql-mcp-server",
      "env": {
        "PGHOST": "localhost",
        "PGPORT": "5432",
        "PGDATABASE": "sales",
        "PGUSER": "mcp_readonly",
        "PGPASSWORD": "change_me"
      }
    }
  }
}
```

Restart Claude Desktop, then ask something like *"What tables are available,
and which product category has the highest total revenue?"*

## Web console (optional)

A browser UI to try the six tools by hand — it imports the **same** `db.py`
and `security.py` as the MCP server, so injection attempts are rejected by
the real validation code, not a re-implementation. Standard library only.

```bash
python -m web.console      # then open http://localhost:8765
```

Needs the same Postgres / `.env` as the server.

## Sample schema

`orders` → `order_items` → `products` → `categories`, plus `customers`.
Revenue for an order = `sum(order_items.quantity * order_items.unit_price)`.
The generator seeds ~600 customers, ~3,500 orders, and a handful of
intentional data quirks (missing emails, a few bulk-order outliers) so
queries look like they're hitting real data.

## Testing

`tests/test_security.py` and `tests/test_tools.py` run without a database —
they test the validation layer directly and the tool functions with the DB
layer mocked. This is what CI runs. `db.py` itself (the psycopg2 layer) is
exercised in practice by running the server against the Docker Postgres
instance; see Quickstart above.

## Project structure

```
sql_mcp_server/
  config.py    Environment-based settings
  security.py  SQL/identifier validation (the core safety logic)
  db.py        psycopg2 access layer
  server.py    MCP tool definitions
web/
  console.py   Optional browser console over db.py + security.py
scripts/
  init_schema.sql            Schema + read-only role setup
  generate_sample_data.py    Faker-based sample data
tests/
  test_security.py  Validation logic (18+ cases: injection, stacked
                     statements, comment smuggling, DDL/DML blocking, etc.)
  test_tools.py     Tool functions with mocked DB
```
