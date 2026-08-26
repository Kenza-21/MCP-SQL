import pytest

from sql_mcp_server import security
from sql_mcp_server.security import UnsafeQueryError


class TestValidateIdentifier:
    def test_valid_known_identifier_passes(self):
        assert security.validate_identifier("orders", known_names={"orders", "customers"}) == "orders"

    def test_unknown_identifier_rejected(self):
        with pytest.raises(UnsafeQueryError, match="Unknown table"):
            security.validate_identifier("orders", known_names={"customers"}, kind="table")

    @pytest.mark.parametrize(
        "bad_name",
        [
            "orders; DROP TABLE customers",
            "orders--",
            "orders/*",
            "1orders",
            "orders table",
            "",
            "orders'",
        ],
    )
    def test_malformed_identifier_rejected(self, bad_name):
        with pytest.raises(UnsafeQueryError):
            security.validate_identifier(bad_name, known_names={bad_name})


class TestValidateSelectQuery:
    def test_simple_select_passes(self):
        sql = "SELECT * FROM orders"
        assert security.validate_select_query(sql, max_length=4000) == sql

    def test_with_cte_passes(self):
        sql = "WITH t AS (SELECT 1) SELECT * FROM t"
        assert security.validate_select_query(sql, max_length=4000) == sql

    def test_trailing_semicolon_stripped(self):
        result = security.validate_select_query("SELECT 1;", max_length=4000)
        assert result == "SELECT 1"

    def test_empty_query_rejected(self):
        with pytest.raises(UnsafeQueryError, match="empty"):
            security.validate_select_query("   ", max_length=4000)

    def test_too_long_rejected(self):
        with pytest.raises(UnsafeQueryError, match="max length"):
            security.validate_select_query("SELECT " + "1" * 5000, max_length=100)

    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO orders VALUES (1)",
            "UPDATE orders SET status = 'x'",
            "DELETE FROM orders",
            "DROP TABLE orders",
            "ALTER TABLE orders ADD COLUMN x TEXT",
            "TRUNCATE orders",
            "GRANT ALL ON orders TO public",
            "CREATE TABLE evil (id INT)",
        ],
    )
    def test_write_statements_rejected(self, sql):
        with pytest.raises(UnsafeQueryError):
            security.validate_select_query(sql, max_length=4000)

    def test_stacked_statements_rejected(self):
        sql = "SELECT 1; DROP TABLE orders;"
        with pytest.raises(UnsafeQueryError, match="Multiple statements"):
            security.validate_select_query(sql, max_length=4000)

    def test_sql_comment_smuggling_rejected(self):
        # This particular payload trips the semicolon check first (it's
        # checked before comments), which is fine -- it's still rejected.
        with pytest.raises(UnsafeQueryError, match="Multiple statements"):
            security.validate_select_query(
                "SELECT * FROM orders -- ; DROP TABLE customers",
                max_length=4000,
            )

    def test_sql_comment_without_semicolon_rejected(self):
        # A comment with no semicolon should be caught by the dedicated
        # comment check.
        with pytest.raises(UnsafeQueryError, match="comments"):
            security.validate_select_query(
                "SELECT * FROM orders -- sneaky trailing comment",
                max_length=4000,
            )

    def test_non_select_start_rejected(self):
        with pytest.raises(UnsafeQueryError, match="Only SELECT"):
            security.validate_select_query("EXPLAIN SELECT 1", max_length=4000)

    def test_select_into_rejected(self):
        # SELECT ... INTO creates a new table -- must be blocked even though
        # it starts with SELECT.
        with pytest.raises(UnsafeQueryError, match="(?i)into"):
            security.validate_select_query(
                "SELECT * INTO new_table FROM orders", max_length=4000
            )


class TestEnforceRowLimit:
    def test_adds_limit_when_missing(self):
        result = security.enforce_row_limit("SELECT * FROM orders", max_rows=500)
        assert "LIMIT 500" in result

    def test_keeps_limit_under_cap(self):
        result = security.enforce_row_limit("SELECT * FROM orders LIMIT 10", max_rows=500)
        assert result == "SELECT * FROM orders LIMIT 10"

    def test_caps_limit_over_max(self):
        result = security.enforce_row_limit("SELECT * FROM orders LIMIT 99999", max_rows=500)
        assert "LIMIT 500" in result
        assert "99999" not in result
