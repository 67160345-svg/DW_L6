import pandas as pd
from .config import PROVINCE_MAP


def _standardize_province(value):
    if pd.isna(value) or str(value).strip() == "":
        return "Unknown"
    key = str(value).strip().lower()
    return PROVINCE_MAP.get(key, "Unknown")


def _clean_price(value):
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value):
    """Try several known formats seen in the source data."""
    text = str(value).strip()
    for fmt in ("%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y"):
        try:
            return pd.to_datetime(text, format=fmt)
        except (ValueError, TypeError):
            continue
    return pd.NaT


def transform_data(raw):
    """
    Clean customers/products/orders, merge them into `sales`,
    and collect every rejected row (with a reason) into `rejects`.
    """

    customers_raw = raw["customers"]
    orders_raw = raw["orders"]
    products_raw = raw["products"]

    # ------------------------------------------------------------------
    # Customers: dedupe on customer_id, standardize province, fill email
    # ------------------------------------------------------------------
    customers = customers_raw.drop_duplicates(subset="customer_id", keep="first").copy()
    customers["province"] = customers["province"].apply(_standardize_province)
    customers["email"] = customers["email"].fillna("unknown")
    customers.loc[customers["email"].astype(str).str.strip() == "", "email"] = "unknown"

    # ------------------------------------------------------------------
    # Products: flatten (already done via json_normalize in extract),
    # rename, coerce price to numeric, fill missing category
    # ------------------------------------------------------------------
    products = products_raw.rename(
        columns={"category.name": "category", "pricing.price": "price"}
    ).copy()
    products["price"] = products["price"].apply(_clean_price)
    products["category"] = products["category"].fillna("Unknown")
    products.loc[products["category"].astype(str).str.strip() == "", "category"] = "Unknown"
    products = products[["product_id", "product_name", "category", "price"]]

    # ------------------------------------------------------------------
    # Orders: clean + validate, collecting rejects with reasons along the way
    # ------------------------------------------------------------------
    orders = orders_raw.copy()
    orders["status"] = orders["status"].astype(str).str.strip().str.lower()

    reject_frames = []

    # 1) duplicate order_id -> keep first occurrence, reject the rest
    dup_mask = orders.duplicated(subset="order_id", keep="first")
    if dup_mask.any():
        dup_rej = orders[dup_mask].copy()
        dup_rej["reject_reason"] = "duplicate_order_id"
        reject_frames.append(dup_rej)
    orders = orders[~dup_mask].copy()

    # 2) parse mixed date formats
    orders["order_date_parsed"] = orders["order_date"].apply(_parse_date)

    invalid_date = orders["order_date_parsed"].isna()
    invalid_qty = orders["qty"] <= 0
    invalid_price = orders["unit_price"] <= 0
    invalid_discount = (orders["discount_pct"] < 0) | (orders["discount_pct"] > 100)
    invalid_mask = invalid_date | invalid_qty | invalid_price | invalid_discount

    def _reason(row):
        reasons = []
        if pd.isna(row["order_date_parsed"]):
            reasons.append("invalid_date")
        if row["qty"] <= 0:
            reasons.append("invalid_qty")
        if row["unit_price"] <= 0:
            reasons.append("invalid_unit_price")
        if row["discount_pct"] < 0 or row["discount_pct"] > 100:
            reasons.append("invalid_discount_pct")
        return ";".join(reasons)

    if invalid_mask.any():
        inv_rej = orders[invalid_mask].copy()
        inv_rej["reject_reason"] = inv_rej.apply(_reason, axis=1)
        inv_rej = inv_rej.drop(columns=["order_date_parsed"])
        reject_frames.append(inv_rej)

    orders_valid = orders[~invalid_mask].copy()
    orders_valid["order_date"] = orders_valid["order_date_parsed"]
    orders_valid = orders_valid.drop(columns=["order_date_parsed"])

    # 3) keep only paid / completed orders
    status_mask = orders_valid["status"].isin(["paid", "completed"])
    dropped_status = orders_valid[~status_mask].copy()
    if len(dropped_status):
        dropped_status["reject_reason"] = "status_not_paid_or_completed"
        reject_frames.append(dropped_status)
    orders_valid = orders_valid[status_mask].copy()

    # 4) join with customers + products; unknown keys -> reject
    merged = orders_valid.merge(
        customers[["customer_id"]], on="customer_id", how="left", indicator="cust_ind"
    )
    merged = merged.merge(
        products[["product_id"]], on="product_id", how="left", indicator="prod_ind"
    )

    unknown_mask = (merged["cust_ind"] == "left_only") | (merged["prod_ind"] == "left_only")
    if unknown_mask.any():
        unk_rej = merged[unknown_mask].copy()

        def _unk_reason(row):
            reasons = []
            if row["cust_ind"] == "left_only":
                reasons.append("unknown_customer_id")
            if row["prod_ind"] == "left_only":
                reasons.append("unknown_product_id")
            return ";".join(reasons)

        unk_rej["reject_reason"] = unk_rej.apply(_unk_reason, axis=1)
        unk_rej = unk_rej.drop(columns=["cust_ind", "prod_ind"])
        reject_frames.append(unk_rej)

    sales_base = merged[~unknown_mask].drop(columns=["cust_ind", "prod_ind"]).copy()

    # 5) calculate amounts
    sales_base["gross_amount"] = sales_base["qty"] * sales_base["unit_price"]
    sales_base["discount_amount"] = sales_base["gross_amount"] * sales_base["discount_pct"] / 100
    sales_base["sales_amount"] = sales_base["gross_amount"] - sales_base["discount_amount"]

    sales = sales_base[
        ["order_id", "customer_id", "product_id", "order_date", "qty",
         "unit_price", "discount_pct", "sales_amount"]
    ].reset_index(drop=True)

    if reject_frames:
        rejects = pd.concat(reject_frames, ignore_index=True, sort=False)
        cols = list(orders_raw.columns) + ["reject_reason"]
        rejects = rejects[cols]
    else:
        rejects = pd.DataFrame(columns=list(orders_raw.columns) + ["reject_reason"])

    return customers, products, sales, rejects
