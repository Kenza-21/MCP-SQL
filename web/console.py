"""
Web console — a small interface to explore the SQL MCP Server's tools from a
browser, using the *same* database layer and security checks as the MCP
server itself.

This is a demonstration / inspection UI only. It does not touch the MCP
protocol layer (`sql_mcp_server/server.py`); it imports `db` and `security`
directly, so what you see here is exactly what an LLM agent would get.

Run:
    python -m web.console            # then open http://localhost:8765

Requires the same env / .env as the MCP server (read-only Postgres role).
Standard library only — no extra dependencies.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from sql_mcp_server import security
from sql_mcp_server.config import settings
from sql_mcp_server.db import Database

db = Database(settings)

PORT = 8765

PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>SQL MCP Server — console</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  :root { --bg:#0d1117; --panel:#161b22; --panel2:#10151d; --line:#2b3444; --tx:#e6edf3;
    --mut:#8b949e; --acc:#7c72ff; --green:#3fb950; --red:#f85149; --blue:#58a6ff; --amber:#d29922;
    --mono:ui-monospace,"Cascadia Code",Consolas,monospace; --sans:"Segoe UI",system-ui,Roboto,sans-serif; }
  body { background:var(--bg); color:var(--tx); font-family:var(--sans); font-size:14px;
    display:grid; grid-template-columns:300px 1fr; min-height:100vh; }
  @media (max-width:820px){ body{ grid-template-columns:1fr; } }
  .side { background:var(--panel2); border-right:1px solid var(--line); padding:20px 18px; }
  .srv { display:flex; align-items:center; gap:10px; font-weight:700; }
  .srv .d { width:9px; height:9px; border-radius:50%; background:var(--green); box-shadow:0 0 8px var(--green); }
  .srv small { display:block; color:var(--mut); font-weight:400; font-family:var(--mono); font-size:11px; margin-top:3px; }
  .sect { font-family:var(--mono); font-size:10px; letter-spacing:.2em; text-transform:uppercase; color:var(--mut); margin:22px 0 10px; }
  .tool { display:flex; align-items:center; gap:9px; font-family:var(--mono); font-size:12.5px; padding:9px 10px;
    border-radius:6px; color:#c9d1d9; cursor:pointer; border:1px solid transparent; }
  .tool:hover { background:rgba(124,114,255,.08); }
  .tool.on { background:rgba(124,114,255,.14); color:#fff; border-color:rgba(124,114,255,.35); }
  .tool .t { color:var(--acc); }
  .sec-note { margin-top:20px; font-family:var(--mono); font-size:11px; line-height:1.9; color:var(--mut);
    border:1px solid var(--line); border-radius:8px; padding:12px 13px; }
  .sec-note b { color:var(--green); }

  .main { padding:24px 30px; }
  .bar { display:flex; align-items:center; gap:12px; padding-bottom:16px; border-bottom:1px solid var(--line); }
  .bar h1 { font-size:16px; font-weight:700; }
  .bar .who { margin-left:auto; font-family:var(--mono); font-size:11px; color:var(--mut); }
  form { margin-top:18px; display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
  input, textarea { font:inherit; background:var(--panel); border:1px solid var(--line); color:var(--tx);
    border-radius:8px; padding:10px 12px; }
  input { width:240px; } textarea { width:100%; font-family:var(--mono); font-size:12.5px; min-height:70px; }
  button { font:inherit; background:var(--acc); color:#0b0714; font-weight:700; border:0; border-radius:8px;
    padding:10px 18px; cursor:pointer; }
  button:disabled { opacity:.5; cursor:default; }
  .hint { font-family:var(--mono); font-size:11px; color:var(--mut); }
  .quick { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
  .quick button { background:var(--panel); color:var(--mut); border:1px solid var(--line); font-weight:400; font-size:11px;
    font-family:var(--mono); padding:6px 10px; }

  .out { margin-top:18px; }
  .status { font-family:var(--mono); font-size:12px; display:flex; align-items:center; gap:8px; margin-bottom:8px; }
  .status.ok { color:var(--green); } .status.err { color:var(--red); }
  table { width:100%; border-collapse:collapse; font-family:var(--mono); font-size:12px;
    border:1px solid var(--line); border-radius:8px; overflow:hidden; display:block; overflow-x:auto; }
  th { text-align:left; background:var(--panel); color:var(--mut); padding:8px 12px; border-bottom:1px solid var(--line);
    font-size:11px; position:sticky; top:0; }
  td { padding:7px 12px; border-bottom:1px solid #1c2230; white-space:nowrap; }
  pre { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px 16px;
    font-family:var(--mono); font-size:12px; white-space:pre-wrap; word-break:break-word; max-height:440px; overflow:auto; }
  .k { color:var(--blue); } .s { color:var(--green); } .n { color:var(--amber); }
</style></head><body>
<div class="side">
  <div class="srv"><span class="d"></span><div>sql-mcp-server<small id="conn">PostgreSQL &middot; lecture seule</small></div></div>
  <div class="sect">outils exposés (6)</div>
  <div class="tool on" data-tool="list_tables"><span class="t">&#9656;</span> list_tables</div>
  <div class="tool" data-tool="describe_table"><span class="t">&#9656;</span> describe_table</div>
  <div class="tool" data-tool="search_schema"><span class="t">&#9656;</span> search_schema</div>
  <div class="tool" data-tool="sample_rows"><span class="t">&#9656;</span> sample_rows</div>
  <div class="tool" data-tool="count_rows"><span class="t">&#9656;</span> count_rows</div>
  <div class="tool" data-tool="execute_select"><span class="t">&#9656;</span> execute_select</div>
  <div class="sec-note">
    rôle : <b>mcp_readonly</b><br />DDL / DML &rarr; bloqué<br />requêtes empilées &rarr; bloqué<br />
    commentaires SQL &rarr; bloqué<br /><b>SET TRANSACTION READ ONLY</b> par connexion
  </div>
</div>
<div class="main">
  <div class="bar"><h1 id="title">list_tables()</h1><span class="who">console web &middot; mêmes db.py / security.py que le serveur MCP</span></div>
  <form id="form"><span id="fields"></span><button id="run" type="submit">Exécuter</button></form>
  <div class="quick" id="quick"></div>
  <div class="out" id="out"><span class="hint">Choisissez un outil et exécutez-le.</span></div>
</div>
<script>
const TOOLS = {
  list_tables:    { args: [], title: "list_tables()" },
  describe_table: { args: [["table","table"]], title: "describe_table(table)" },
  search_schema:  { args: [["keyword","email"]], title: "search_schema(keyword)" },
  sample_rows:    { args: [["table","table"],["limit","5"]], title: "sample_rows(table, limit)" },
  count_rows:     { args: [["table","table"]], title: "count_rows(table)" },
  execute_select: { args: [["sql","SELECT 1"]], title: "execute_select(sql)", textarea: true },
};
const QUICK = {
  execute_select: [
    "SELECT * FROM information_schema.tables WHERE table_schema='public' LIMIT 5",
    "SELECT * FROM customers; DROP TABLE customers; --",
    "UPDATE customers SET email='x' WHERE id=1",
  ],
};
let current = "list_tables";
const $ = (s) => document.querySelector(s);

function render() {
  const spec = TOOLS[current];
  $("#title").textContent = spec.title;
  document.querySelectorAll(".tool").forEach(t => t.classList.toggle("on", t.dataset.tool === current));
  const f = $("#fields"); f.innerHTML = "";
  for (const [name, ph] of spec.args) {
    const el = document.createElement(spec.textarea ? "textarea" : "input");
    el.name = name; el.placeholder = name + "  (ex: " + ph + ")"; f.appendChild(el);
  }
  const q = $("#quick"); q.innerHTML = "";
  (QUICK[current] || []).forEach(s => {
    const b = document.createElement("button"); b.type = "button"; b.textContent = s.slice(0, 46) + (s.length > 46 ? "…" : "");
    b.onclick = () => { const ta = f.querySelector("[name=sql]"); if (ta) ta.value = s; };
    q.appendChild(b);
  });
  $("#out").innerHTML = '<span class="hint">Prêt.</span>';
}

document.querySelectorAll(".tool").forEach(t => t.onclick = () => { current = t.dataset.tool; render(); });

function tableHTML(rows) {
  if (!rows.length) return '<span class="hint">0 ligne.</span>';
  const cols = Object.keys(rows[0]);
  let h = "<table><thead><tr>" + cols.map(c => "<th>" + c + "</th>").join("") + "</tr></thead><tbody>";
  for (const r of rows.slice(0, 200))
    h += "<tr>" + cols.map(c => "<td>" + String(r[c] ?? "∅") + "</td>").join("") + "</tr>";
  return h + "</tbody></table>";
}

$("#form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#run"); btn.disabled = true; btn.textContent = "…";
  const params = {};
  new FormData(e.target).forEach((v, k) => params[k] = v);
  const t0 = performance.now();
  try {
    const res = await fetch("/api/" + current, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(params),
    });
    const body = await res.json();
    const ms = Math.round(performance.now() - t0);
    const out = $("#out");
    if (body.error) {
      out.innerHTML = '<div class="status err">&#10005; rejeté &mdash; ' + body.error + '</div>';
    } else if (Array.isArray(body.result)) {
      out.innerHTML = '<div class="status ok">&#10003; ' + body.result.length + ' ligne(s) &middot; ' + ms + ' ms</div>' + tableHTML(body.result);
    } else if (body.result && Array.isArray(body.result.rows)) {
      out.innerHTML = '<div class="status ok">&#10003; ' + body.result.row_count + ' ligne(s) &middot; ' + ms + ' ms</div>' + tableHTML(body.result.rows);
    } else {
      out.innerHTML = '<div class="status ok">&#10003; ' + ms + ' ms</div><pre>' + JSON.stringify(body.result, null, 2) + '</pre>';
    }
  } catch (err) {
    $("#out").innerHTML = '<div class="status err">&#10005; ' + err.message + '</div>';
  } finally {
    btn.disabled = false; btn.textContent = "Exécuter";
  }
});
render();
</script>
</body></html>
"""


def _run_tool(name: str, params: dict) -> dict:
    """Call the requested tool through the real db + security layers."""
    try:
        if name == "list_tables":
            return {"result": db.list_tables()}
        if name == "search_schema":
            return {"result": db.search_schema(params.get("keyword", ""))}
        if name == "describe_table":
            table = params.get("table", "")
            security.validate_identifier(table, known_names=db.known_table_names(), kind="table")
            return {"result": {
                "table": table,
                "columns": db.describe_table_columns(table),
                "constraints": db.describe_table_constraints(table),
            }}
        if name == "sample_rows":
            table = params.get("table", "")
            security.validate_identifier(table, known_names=db.known_table_names(), kind="table")
            limit = min(int(params.get("limit") or 5), settings.max_rows)
            return {"result": db.sample_rows(table, limit)}
        if name == "count_rows":
            table = params.get("table", "")
            security.validate_identifier(table, known_names=db.known_table_names(), kind="table")
            return {"result": {"table": table, "row_count": db.count_rows(table)}}
        if name == "execute_select":
            validated = security.validate_select_query(
                params.get("sql", ""), max_length=settings.max_query_length
            )
            limited = security.enforce_row_limit(validated, max_rows=settings.max_rows)
            rows = db.execute_select(limited)
            return {"result": {"row_count": len(rows), "rows": rows}}
        return {"error": f"unknown tool '{name}'"}
    except security.UnsafeQueryError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # DB unreachable, bad identifier, timeout, ...
        return {"error": f"{type(exc).__name__}: {exc}"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quieter console
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if not self.path.startswith("/api/"):
            self._send(404, b"not found", "text/plain")
            return
        name = self.path[len("/api/"):]
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            params = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            params = {}
        result = _run_tool(name, params if isinstance(params, dict) else {})
        self._send(200, json.dumps(result, default=str).encode("utf-8"), "application/json")


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"SQL MCP console -> http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
