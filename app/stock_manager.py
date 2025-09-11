import pandas as pd

def _normalize_sales(df: pd.DataFrame) -> pd.DataFrame:
    # Нормалізація назв колонок у sales
    df = df.rename(columns={c: c.strip().lower() for c in df.columns})

    if "qty" not in df.columns:
        if "units_sold" in df.columns:
            df = df.rename(columns={"units_sold": "qty"})
        else:
            raise KeyError("Не знайдено колонку 'qty' або 'units_sold' у sales.csv")

    if "sku" not in df.columns:
        raise KeyError("Не знайдено колонку 'sku' у sales.csv")

    if "date" not in df.columns:
        raise KeyError("Не знайдено колонку 'date' у sales.csv")

    return df[["date", "sku", "qty"]]


def _normalize_inventory(df: pd.DataFrame) -> pd.DataFrame:
    # Нормалізація назв колонок у inventory
    df = df.rename(columns={c: c.strip().lower() for c in df.columns})

    if "stock" not in df.columns:
        if "on_hand" in df.columns:
            df = df.rename(columns={"on_hand": "stock"})
        else:
            raise KeyError("Не знайдено колонку 'stock' або 'on_hand' в inventory.csv")

    if "sku" not in df.columns:
        raise KeyError("Не знайдено колонку 'sku' в inventory.csv")

    if "name" not in df.columns:
        df["name"] = df["sku"]

    return df[["sku", "name", "stock"]]


def _daily_avg(sales_df: pd.DataFrame) -> pd.Series:
    sales_df = _normalize_sales(sales_df)
    daily = sales_df.groupby("sku")["qty"].mean().rename("avg_daily_qty")
    return daily


def _calc_po(df: pd.DataFrame, safety_days: float = 2.0) -> pd.DataFrame:
    # Формула: need_qty = avg_daily_qty * safety_days - stock
    df = df.copy()
    df["need_qty"] = (df["avg_daily_qty"] * safety_days - df["stock"]).round().astype(int)
    po = df[df["need_qty"] > 0][["sku", "name", "need_qty"]].sort_values("sku")
    return po


def build_purchase_order(sales_path: str, inv_path: str):
    # Читаємо sales з fallback на cp1251
    try:
        sales = pd.read_csv(sales_path, encoding="utf-8")
    except UnicodeDecodeError:
        sales = pd.read_csv(sales_path, encoding="cp1251")

    # Читаємо inventory з fallback на cp1251
    try:
        inv = pd.read_csv(inv_path, encoding="utf-8")
    except UnicodeDecodeError:
        inv = pd.read_csv(inv_path, encoding="cp1251")

    inv = _normalize_inventory(inv)
    daily_avg = _daily_avg(sales)

    merged = inv.merge(daily_avg, on="sku", how="left").fillna({"avg_daily_qty": 0})
    po = _calc_po(merged)

    # Підсумок у вигляді тексту
    if len(po):
        lines = [f"PO дата: {pd.Timestamp.today().date()}"]
        for _, r in po.iterrows():
            lines.append(f"{r['sku']}: {r['name']} — {int(r['need_qty'])} шт.")
        summary = "\n".join(lines)
    else:
        summary = "Замовлень немає — запас достатній."

    return po, summary
