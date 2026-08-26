"""
Tests the tool functions in server.py with the Database layer mocked out,
so they run without a live Postgres instance. db.py itself is exercised by
integration tests (see tests/test_db_integration.py) against the Docker DB.
"""
from unittest.mock import MagicMock

import pytest

from sql_mcp_server import server


@pytest.fixture
def fake_db(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(server, "db", fake)
    return fake


def test_list_tables_returns_db_result(fake_db):
    fake_db.list_tables.return_value = [{"table_name": "orders"}]
    result = server.list_tables()
    assert result == [{"table_name": "orders"}]


def test_describe_table_validates_against_known_tables(fake_db):
    fake_db.known_table_names.return_value = {"orders", "customers"}
    fake_db.describe_table_columns.return_value = [{"column_name": "order_id"}]
    fake_db.describe_table_constraints.return_value = []

    result = server.describe_table("orders")

    assert result["table"] == "orders"
    assert result["columns"] == [{"column_name": "order_id"}]


def test_describe_table_rejects_unknown_table(fake_db):
    fake_db.known_table_names.return_value = {"orders"}
    with pytest.raises(Exception):
        server.describe_table("nonexistent_table")


def test_describe_table_rejects_injection_attempt(fake_db):
    fake_db.known_table_names.return_value = {"orders"}
    with pytest.raises(Exception):
        server.describe_table("orders; DROP TABLE customers;")


def test_sample_rows_caps_limit_at_server_max(fake_db, monkeypatch):
    from dataclasses import replace

    fake_db.known_table_names.return_value = {"orders"}
    fake_db.sample_rows.return_value = []
    monkeypatch.setattr(server, "settings", replace(server.settings, max_rows=10))

    server.sample_rows("orders", limit=999999)

    called_table, called_limit = fake_db.sample_rows.call_args[0]
    assert called_limit == 10


def test_count_rows_validates_table(fake_db):
    fake_db.known_table_names.return_value = {"orders"}
    fake_db.count_rows.return_value = 42

    result = server.count_rows("orders")

    assert result == {"table": "orders", "row_count": 42}


def test_execute_select_runs_valid_query(fake_db):
    fake_db.execute_select.return_value = [{"total": 100}]

    result = server.execute_select("SELECT sum(unit_price) AS total FROM order_items")

    assert result["row_count"] == 1
    assert result["rows"] == [{"total": 100}]
    fake_db.execute_select.assert_called_once()


def test_execute_select_blocks_write_query_without_touching_db(fake_db):
    result = server.execute_select("DELETE FROM orders")

    assert "error" in result
    fake_db.execute_select.assert_not_called()


def test_execute_select_blocks_stacked_statements(fake_db):
    result = server.execute_select("SELECT 1; DROP TABLE orders;")

    assert "error" in result
    fake_db.execute_select.assert_not_called()
