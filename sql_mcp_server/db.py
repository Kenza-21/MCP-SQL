"""
Thin database access layer over psycopg2.

Every connection:
  - uses the read-only role configured in Settings
  - starts each transaction with SET TRANSACTION READ ONLY
  - sets a statement_timeout so a runaway query can't hang the server

This module has no knowledge of MCP; it's plain Python so it can be unit
tested without spinning up the MCP protocol layer.
"""
from __future__ import annotations

import contextlib
from typing import Any, Iterator

import psycopg2
import psycopg2.extras

from .config import Settings


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _connect(self):
        conn = psycopg2.connect(
            host=self.settings.pg_host,
            port=self.settings.pg_port,
            dbname=self.settings.pg_db,
            user=self.settings.pg_user,
            password=self.settings.pg_password,
        )
        conn.set_session(readonly=True, autocommit=False)
        return conn

    @contextlib.contextmanager
    def cursor(self) -> Iterator["psycopg2.extras.RealDictCursor"]:
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"SET statement_timeout = {int(self.settings.statement_timeout_ms)}"
                )
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ---- schema introspection -------------------------------------------------

    def list_tables(self) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT c.relname AS table_name,
                       obj_description(c.oid) AS description,
                       pg_size_pretty(pg_total_relation_size(c.oid)) AS size,
                       (SELECT count(*) FROM information_schema.columns
                          WHERE table_name = c.relname AND table_schema = 'public') AS column_count
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'r' AND n.nspname = 'public'
                ORDER BY c.relname
                """
            )
            return list(cur.fetchall())

    def known_table_names(self) -> set[str]:
        return {row["table_name"] for row in self.list_tables()}

    def known_column_names(self, table: str) -> set[str]:
        return {col["column_name"] for col in self.describe_table_columns(table)}

    def describe_table_columns(self, table: str) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default,
                       character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table,),
            )
            return list(cur.fetchall())

    def describe_table_constraints(self, table: str) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT
                    tc.constraint_type,
                    kcu.column_name,
                    ccu.table_name AS foreign_table,
                    ccu.column_name AS foreign_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                LEFT JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name
                    AND tc.constraint_type = 'FOREIGN KEY'
                WHERE tc.table_schema = 'public' AND tc.table_name = %s
                """,
                (table,),
            )
            return list(cur.fetchall())

    def search_schema(self, keyword: str) -> list[dict[str, Any]]:
        like = f"%{keyword}%"
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND (table_name ILIKE %s OR column_name ILIKE %s)
                ORDER BY table_name, ordinal_position
                """,
                (like, like),
            )
            return list(cur.fetchall())

    # ---- data access ------------------------------------------------------

    def sample_rows(self, table: str, limit: int) -> list[dict[str, Any]]:
        # table name must already be validated by caller against known_table_names()
        with self.cursor() as cur:
            cur.execute(f'SELECT * FROM "{table}" LIMIT %s', (limit,))
            return list(cur.fetchall())

    def count_rows(self, table: str) -> int:
        with self.cursor() as cur:
            cur.execute(f'SELECT count(*) AS n FROM "{table}"')
            return cur.fetchone()["n"]

    def execute_select(self, sql: str) -> list[dict[str, Any]]:
        # sql must already be validated by caller (security.validate_select_query)
        with self.cursor() as cur:
            cur.execute(sql)
            return list(cur.fetchall())
