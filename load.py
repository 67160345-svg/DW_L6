import sqlite3
from .config import WAREHOUSE_DB


def load_data(customers, products, sales):
    """
    Create/load the warehouse tables:
      dim_customer, dim_product, fact_sales

    - customer_id unique in dim_customer  -> upsert (INSERT OR REPLACE)
    - product_id unique in dim_product    -> upsert (INSERT OR REPLACE)
    - order_id unique in fact_sales       -> INSERT OR IGNORE so a
      second run of the pipeline does NOT duplicate fact_sales rows.
    """
    WAREHOUSE_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(WAREHOUSE_DB)
    cur = con.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS dim_customer (
            customer_id TEXT PRIMARY KEY,
            name        TEXT,
            province    TEXT,
            email       TEXT
        );

        CREATE TABLE IF NOT EXISTS dim_product (
            product_id   TEXT PRIMARY KEY,
            product_name TEXT,
            category     TEXT,
            price        REAL
        );

        CREATE TABLE IF NOT EXISTS fact_sales (
            order_id      TEXT PRIMARY KEY,
            customer_id   TEXT,
            product_id    TEXT,
            order_date    TEXT,
            qty           INTEGER,
            unit_price    REAL,
            discount_pct  REAL,
            sales_amount  REAL
        );
        """
    )

    cur.executemany(
        "INSERT OR REPLACE INTO dim_customer (customer_id, name, province, email) "
        "VALUES (?, ?, ?, ?)",
        customers[["customer_id", "name", "province", "email"]].itertuples(index=False, name=None),
    )

    cur.executemany(
        "INSERT OR REPLACE INTO dim_product (product_id, product_name, category, price) "
        "VALUES (?, ?, ?, ?)",
        products[["product_id", "product_name", "category", "price"]].itertuples(index=False, name=None),
    )

    sales_to_load = sales.copy()
    sales_to_load["order_date"] = sales_to_load["order_date"].astype(str)

    cur.executemany(
        "INSERT OR IGNORE INTO fact_sales "
        "(order_id, customer_id, product_id, order_date, qty, unit_price, discount_pct, sales_amount) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        sales_to_load[
            ["order_id", "customer_id", "product_id", "order_date",
             "qty", "unit_price", "discount_pct", "sales_amount"]
        ].itertuples(index=False, name=None),
    )

    con.commit()
    con.close()
