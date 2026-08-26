-- Sample e-commerce schema for the SQL MCP Server demo.
-- Run this against a fresh database before running generate_sample_data.py.

CREATE TABLE IF NOT EXISTS categories (
    category_id     SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE
);
COMMENT ON TABLE categories IS 'Product categories (e.g. Electronics, Home, Books).';

CREATE TABLE IF NOT EXISTS products (
    product_id      SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    category_id     INTEGER REFERENCES categories(category_id),
    unit_price      NUMERIC(10, 2) NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT now()
);
COMMENT ON TABLE products IS 'Catalog of sellable products.';

CREATE TABLE IF NOT EXISTS customers (
    customer_id     SERIAL PRIMARY KEY,
    full_name       TEXT NOT NULL,
    email           TEXT UNIQUE,
    signup_date     DATE NOT NULL,
    country         TEXT
);
COMMENT ON TABLE customers IS 'Registered customers.';

CREATE TABLE IF NOT EXISTS orders (
    order_id        SERIAL PRIMARY KEY,
    customer_id     INTEGER REFERENCES customers(customer_id),
    order_date      TIMESTAMP NOT NULL,
    status          TEXT NOT NULL DEFAULT 'completed'
);
COMMENT ON TABLE orders IS 'One row per customer order.';

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id   SERIAL PRIMARY KEY,
    order_id        INTEGER REFERENCES orders(order_id),
    product_id      INTEGER REFERENCES products(product_id),
    quantity        INTEGER NOT NULL,
    unit_price      NUMERIC(10, 2) NOT NULL
);
COMMENT ON TABLE order_items IS 'Line items within an order; revenue = quantity * unit_price.';

-- Read-only role used by the MCP server. Change the password before real use.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'mcp_readonly') THEN
        CREATE ROLE mcp_readonly LOGIN PASSWORD 'change_me';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE sales TO mcp_readonly;
GRANT USAGE ON SCHEMA public TO mcp_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mcp_readonly;
