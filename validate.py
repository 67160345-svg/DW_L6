import sqlite3
from .config import WAREHOUSE_DB


def validate_data(source_sales):
    """
    Cross-check the transformed (source) data against what actually
    landed in the warehouse.

    Returns a dict with:
    - source_valid_rows
    - warehouse_rows
    - duplicate_order_ids
    - warehouse_total_sales
    - source_total_sales
    - status: PASS / FAIL
    """
    con = sqlite3.connect(WAREHOUSE_DB)
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM fact_sales")
    warehouse_rows = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM (SELECT order_id FROM fact_sales GROUP BY order_id HAVING COUNT(*) > 1)"
    )
    duplicate_order_ids = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(sales_amount), 0) FROM fact_sales")
    warehouse_total_sales = cur.fetchone()[0]

    con.close()

    source_valid_rows = len(source_sales)
    source_total_sales = float(source_sales["sales_amount"].sum())

    status = (
        "PASS"
        if source_valid_rows == warehouse_rows
        and duplicate_order_ids == 0
        and round(source_total_sales, 2) == round(warehouse_total_sales, 2)
        else "FAIL"
    )

    return {
        "source_valid_rows": source_valid_rows,
        "warehouse_rows": warehouse_rows,
        "duplicate_order_ids": duplicate_order_ids,
        "source_total_sales": round(source_total_sales, 2),
        "warehouse_total_sales": round(warehouse_total_sales, 2),
        "status": status,
    }
