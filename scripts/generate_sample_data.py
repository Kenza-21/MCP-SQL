"""
Populate the sample e-commerce database with realistic fake data.

Usage:
    python scripts/generate_sample_data.py

Reads connection info from the same PG* env vars as the server, but connects
as a superuser/owner role (not mcp_readonly) since it needs to write.
Set PGUSER/PGPASSWORD to an admin role before running this, e.g.:

    export PGUSER=postgres
    export PGPASSWORD=postgres
    python scripts/generate_sample_data.py

Data is deliberately a little messy (some nulls, a few outlier orders) so
demo queries look like a real dataset rather than a toy.
"""
from __future__ import annotations

import os
import random
from datetime import datetime, timedelta

import psycopg2
from faker import Faker

fake = Faker()
random.seed(42)
Faker.seed(42)

CATEGORIES = ["Electronics", "Home & Kitchen", "Books", "Sports", "Beauty", "Toys"]

PRODUCTS_PER_CATEGORY = 12
N_CUSTOMERS = 600
N_ORDERS = 3500
MAX_ITEMS_PER_ORDER = 4

COUNTRIES = ["USA", "Canada", "UK", "Germany", "France", "Spain", "Morocco", "India"]


def connect():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("PGDATABASE", "sales"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", "postgres"),
    )


def main() -> None:
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    print("Inserting categories...")
    category_ids = []
    for name in CATEGORIES:
        cur.execute(
            "INSERT INTO categories (name) VALUES (%s) "
            "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
            "RETURNING category_id",
            (name,),
        )
        category_ids.append(cur.fetchone()[0])

    print("Inserting products...")
    product_ids = []
    for cat_id in category_ids:
        for _ in range(PRODUCTS_PER_CATEGORY):
            price = round(random.uniform(5, 800), 2)
            cur.execute(
                "INSERT INTO products (name, category_id, unit_price) "
                "VALUES (%s, %s, %s) RETURNING product_id",
                (fake.catch_phrase(), cat_id, price),
            )
            product_ids.append((cur.fetchone()[0], price))

    print("Inserting customers...")
    customer_ids = []
    for _ in range(N_CUSTOMERS):
        # ~3% of customers have no email on file -- intentional messiness
        email = fake.unique.email() if random.random() > 0.03 else None
        signup = fake.date_between(start_date="-3y", end_date="-1d")
        cur.execute(
            "INSERT INTO customers (full_name, email, signup_date, country) "
            "VALUES (%s, %s, %s, %s) RETURNING customer_id",
            (fake.name(), email, signup, random.choice(COUNTRIES)),
        )
        customer_ids.append(cur.fetchone()[0])

    print("Inserting orders and order_items...")
    now = datetime.now()
    for _ in range(N_ORDERS):
        customer_id = random.choice(customer_ids)
        days_ago = random.randint(0, 365)
        order_date = now - timedelta(days=days_ago, hours=random.randint(0, 23))
        status = random.choices(
            ["completed", "completed", "completed", "refunded", "cancelled"],
            weights=[70, 10, 10, 5, 5],
        )[0]
        cur.execute(
            "INSERT INTO orders (customer_id, order_date, status) "
            "VALUES (%s, %s, %s) RETURNING order_id",
            (customer_id, order_date, status),
        )
        order_id = cur.fetchone()[0]

        n_items = random.randint(1, MAX_ITEMS_PER_ORDER)
        # occasional outlier bulk order to make aggregate queries interesting
        if random.random() < 0.01:
            n_items = random.randint(15, 40)

        for _ in range(n_items):
            product_id, price = random.choice(product_ids)
            qty = random.randint(1, 5)
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
                "VALUES (%s, %s, %s, %s)",
                (order_id, product_id, qty, price),
            )

    conn.commit()
    cur.close()
    conn.close()
    print(
        f"Done. Inserted {len(category_ids)} categories, {len(product_ids)} products, "
        f"{len(customer_ids)} customers, {N_ORDERS} orders."
    )


if __name__ == "__main__":
    main()
