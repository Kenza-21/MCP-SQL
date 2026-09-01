# SQL MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that exposes a
read-only view of a Postgres database to any MCP-compatible AI assistant. Point an
MCP client at it and ask questions like *"which customers placed more than five orders
last month?"* — the assistant explores the schema and queries the data itself, through
the six tools described below.

MCP is a standard protocol that lets an AI assistant call external tools in a structured
way, instead of guessing at raw database credentials or APIs. This server implements the
"tool provider" side of that protocol for a Postgres database.

## What this actually solves

Text-to-SQL demos are common; the part that's actually hard — and where this project
puts its effort — is making `execute_select` safe to hand to an LLM that will generate
arbitrary SQL on its own:

1. **Read-only Postgres role.** The server connects as `mcp_readonly`, a role with
   `SELECT`-only grants (see `scripts/init_schema.sql`). Even a bug in the
   application-level checks below can't cause a write.
2. **Session-level read-only enforcement.** Every connection runs
   `SET TRANSACTION READ ONLY` (`db.py`).
3. **Statement validation** (`security.py`): only a single `SELECT`/`WITH` statement is
   allowed — no stacked statements (`; DROP TABLE ...`), no SQL comments (blocks
   comment-based statement smuggling), and a keyword blocklist covers
   `INSERT`/`UPDATE`/`DELETE`/`DDL`/`GRANT`/etc., including `SELECT ... INTO` (which
   silently creates a table).
4. **Identifier validation.** `describe_table`, `sample_rows`, and `count_rows` take a
   table name as a parameter. Since SQL identifiers can't be parameterized with
   placeholders, table names are checked against a strict regex *and* a live allow-list
   fetched from `information_schema` — not just string-escaped.
5. **Resource limits.** A Postgres `statement_timeout` prevents runaway queries, and a
   server-side row cap is enforced on every query result, even if the caller's query
   didn't specify a `LIMIT`.

If every one of those checks failed at once, the database connection itself still
couldn't write anything — that's the point of layering them.

## Architecture

```
 User question
      │
      ▼
 AI assistant (any MCP client)
      │  decides which tool to call
      ▼
 MCP server (this project, sql_mcp_server/server.py)
      │  validates the request
      ▼
 security.py   — statement / identifier validation
 db.py         — psycopg2 access layer
      │  only if valid
      ▼
 PostgreSQL  (mcp_readonly role, READ ONLY transaction, statement_timeout)
```

The server itself never decides *what* to query — that's the assistant's job. It only
decides whether a given request is safe to run.

## Tools

| Tool | Description |
|---|---|
| `list_tables()` | Overview of every table: name, description, size, column count |
| `describe_table(table)` | Columns, types, and foreign key relationships for one table |
| `search_schema(keyword)` | Find tables/columns whose name matches a keyword |
| `sample_rows(table, limit)` | Peek at real rows (default 5) |
| `count_rows(table)` | Row count for a table |
| `execute_select(sql)` | Run an arbitrary read-only `SELECT` / `WITH ... SELECT` query |

## Sample schema

`orders` → `order_items` → `products` → `categories`, plus `customers`.
Revenue for an order = `sum(order_items.quantity * order_items.unit_price)`.
The generator seeds ~600 customers, ~3,500 orders, and a handful of intentional data
quirks (missing emails, a few bulk-order outliers) so queries look like they're hitting
real data.

## Tech stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| Database | PostgreSQL 16 |
| Protocol | Model Context Protocol (MCP SDK) |
| DB driver | psycopg2 |
| Sample data | Faker |
| Tests | pytest, pytest-asyncio |

## Getting started

### 1. Clone the repository

```bash
git clone https://github.com/Kenza-21/MCP-SQL-Server.git
cd MCP-SQL-Server
```

### 2. Set up Postgres

**Option A — Docker (recommended, matches this repo's defaults):**

```bash
docker compose up -d
```

This starts Postgres 16 and applies `scripts/init_schema.sql` automatically (creates
the sample tables and the `mcp_readonly` role).

**Option B — an existing/native PostgreSQL instance:**

```bash
# Create the database first
psql -U postgres -c "CREATE DATABASE sales;"

# Then apply the schema + read-only role
psql -U postgres -d sales -f scripts/init_schema.sql
```

### 3. Install Python dependencies

```bash
python -m venv venv
# Windows: venv\Scripts\activate | macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

### 4. Generate sample data

Uses an admin/superuser role (not `mcp_readonly`), since it needs to write:

```bash
PGUSER=postgres PGPASSWORD=postgres python scripts/generate_sample_data.py
```

### 5. Configure the server

```bash
cp .env.example .env
# edit .env if your Postgres credentials differ from the defaults
```

### 6. Run the tests

```bash
pytest
```

### 7. Run the server

```bash
python -m sql_mcp_server.server
```

The server speaks MCP over stdio — it's meant to be launched *by* an MCP client, not
run standalone and typed into.

## Connecting an MCP client

Any MCP-compatible client that supports stdio servers can use this configuration shape
(exact file location depends on the client):

```json
{
  "mcpServers": {
    "sql-explorer": {
      "command": "python",
      "args": ["-m", "sql_mcp_server.server"],
      "cwd": "/absolute/path/to/MCP-SQL-Server",
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

Once connected, ask the assistant something like *"What tables are available, and which
product category has the highest total revenue?"* — it will call `list_tables`,
`describe_table`, and `execute_select` on its own to answer.

You can also test the server manually, without any AI assistant, using
[MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector python -m sql_mcp_server.server
```

This opens a local web UI where you can call each tool by hand and inspect the raw
responses — useful for verifying the server works before wiring it into a client.

## Web console (optional)

A small browser UI to try the six tools by hand, independent of any MCP client. It
imports the **same** `db.py` and `security.py` modules as the MCP server itself, so
whatever it rejects (stacked statements, comments, DML/DDL keywords) is rejected by the
real validation logic — not a separate re-implementation that could drift out of sync.
Standard library only, no extra dependencies.

```bash
python -m web.console      # then open http://localhost:8765
```

Requires the same Postgres connection / `.env` as the MCP server.

## Testing

`tests/test_security.py` and `tests/test_tools.py` run without a database — they test
the validation layer directly and the tool functions with the DB layer mocked. This is
what CI runs. `db.py` itself (the psycopg2 layer) is exercised in practice by running
the server against a real Postgres instance; see Getting Started above.

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

## Security notes

- Never commit `.env` — it's already listed in `.gitignore`. Only `.env.example`
  (placeholder values) is tracked.
- The default `mcp_readonly` password (`change_me`) is a placeholder for local
  development. Change it before pointing this at anything that isn't a throwaway
  sample database.
- `execute_select` returns structured `{"error": "..."}` responses for rejected
  queries instead of raising exceptions, so a calling assistant gets a clear reason
  and can retry with a corrected query — it never silently fails.
