import pandas as pd
import numpy as np
from datetime import datetime
from .config import DEFAULT_LEAD_DAYS, DEFAULT_SAFETY_DAYS, TARGET_DAYS_OF_COVER

def _daily_avg(sales_df):
    # очікуємо колонки: date, sku, qty
    daily = sales_df.groupby("sku")["qty"].mean().rename("avg_daily_qty")
    return daily

def _join_inventory(inv_df, daily_avg):
    # очікуємо inventory: sku, stock, lead_days?, safety_days?, target_cover_days?
    df = inv_df.merge(daily_avg, on="sku", how="left").fillna({"avg_daily_qty": 0})
    df["lead_days"] = df.get("lead_days", pd.Series([DEFAULT_LEAD_DAYS]*len(df))).fillna(DEFAULT_LEAD_DAYS)
    df["safety_days"] = df.get("safety_days", pd.Series([DEFAULT_SAFETY_DAYS]*len(df))).fillna(DEFAULT_SAFETY_DAYS)
    df["target_cover_days"] = df.get("target_cover_days", pd.Series([TARGET_DAYS_OF_COVER]*len(df))).fillna(TARGET_DAYS_OF_COVER)
    return df

def _calc_po(df):
    # формула: need = target_cover_days*avg - stock + safety + lead*avg
    df["need_qty"] = (
        df["target_cover_days"] * df["avg_daily_qty"]
        + df["safety_days"] * df["avg_daily_qty"]
        + df["lead_days"] * df["avg_daily_qty"]
        - df["stock"]
    )
    df["need_qty"] = df["need_qty"].clip(lower=0).round().astype(int)
    po = df[df["need_qty"] > 0][["sku", "name", "need_qty"]].sort_values("sku")
    return po

def build_purchase_order(sales_csv, inventory_csv):
    sales = pd.read_csv(sales_csv, parse_dates=["date"])
    inv = pd.read_csv(inventory_csv)

    daily_avg = _daily_avg(sales)
    merged = _join_inventory(inv, daily_avg)
    po = _calc_po(merged)

    date_str = datetime.now().strftime("%Y-%m-%d")
    lines = [f"PO дата: {date_str}", "-"*40]
    total_positions = len(po)
    if total_positions == 0:
        lines.append("Нічого не потрібно замовляти.")
    else:
        for _, r in po.iterrows():
            lines.append(f"{r['sku']}: {r['name']} — {r['need_qty']} шт.")
    report = "\n".join(lines)
    summary = {"date": date_str, "report_text": report}
    return po, summary