# -*- coding: utf-8 -*-
import os
import io
import tempfile
import pandas as pd
import streamlit as st

# Локальний двигун з логікою розрахунку та Telegram-відправкою
import order_engine as oe

# ---------- UI CONFIG ----------
st.set_page_config(page_title="AI Beer Stock Manager", page_icon="🍺", layout="wide")
st.title("🍺 AI Beer Stock Manager — Streamlit")
st.caption("Дві точки (Боголюбова / Європейська, 31а). Ліміти діляться навпіл, замовлення у CSV та в Telegram.")

# ---------- SIDEBAR SETTINGS ----------
with st.sidebar:
    st.header("⚙️ Налаштування")
    out_dir = st.text_input("Папка для CSV (OUT_DIR)", value=os.getenv("OUT_DIR", "out"))
    dry_run = st.checkbox("DRY_RUN (тільки локально, без TG)", value=True)
    tg_token = st.text_input("TELEGRAM_BOT_TOKEN", value=os.getenv("TELEGRAM_BOT_TOKEN", ""), type="password")
    tg_chat  = st.text_input("TELEGRAM_CHAT_ID", value=os.getenv("TELEGRAM_CHAT_ID", "555406850"))
    st.write("---")
    st.caption("Щоб реально надіслати в Telegram — зніміть DRY_RUN, заповніть токен і chat_id, і натисніть «Надіслати в Telegram».")

# ---------- INPUTS ----------
st.subheader("1) Вхідні файли")
c1, c2 = st.columns(2)
with c1:
    stock_file = st.file_uploader("Excel із залишками (export_limits.xlsx / .xls)", type=["xlsx", "xls"])
with c2:
    suppliers_file = st.file_uploader("suppliers.csv або .xlsx/.xls", type=["csv", "xlsx", "xls"])

run_col, send_col = st.columns(2)
btn_run  = run_col.button("🔢 Розрахувати")
btn_send = send_col.button("🚀 Надіслати в Telegram")

# ---------- HELPERS ----------
tmp_dir = tempfile.mkdtemp(prefix="beer_streamlit_")

def save_upload(file, name_hint):
    path = os.path.join(tmp_dir, name_hint)
    with open(path, "wb") as f:
        f.write(file.read())
    return path

# стан між кліками
if "po_a_path" not in st.session_state:
    st.session_state.po_a_path = None
if "po_b_path" not in st.session_state:
    st.session_state.po_b_path = None
if "summary_text" not in st.session_state:
    st.session_state.summary_text = ""

def _fmt_num(x: float) -> str:
    try:
        xf = float(x)
        return f"{int(xf)}" if xf.is_integer() else f"{xf:.2f}"
    except Exception:
        return str(x)

def totals_text(df: pd.DataFrame) -> str:
    """Повертає сумарні обсяги (л/кг/шт) по замовленню."""
    if df.empty:
        return "0"
    sums = df.assign(unit=df["unit"].fillna("шт")).groupby("unit", dropna=False)["order_qty"].sum()
    prefer = ["л", "кг", "шт"]
    parts = [f"{_fmt_num(sums[u])} {u}" for u in prefer if u in sums and sums[u] > 0]
    for u, v in sums.items():
        if u not in prefer and v > 0:
            parts.append(f"{_fmt_num(v)} {u}")
    return ", ".join(parts) if parts else "0"

def top3_text(df: pd.DataFrame) -> str:
    if df.empty:
        return "—"
    x = df.sort_values("order_qty", ascending=False).head(3)
    return ", ".join(f"{r.product_name} — {_fmt_num(r.order_qty)} {r.unit}" for r in x.itertuples())

def line_for_store(store_name: str, df_po: pd.DataFrame) -> str:
    suppliers = df_po["supplier_name"].nunique() if not df_po.empty else 0
    return (
        f"Магазин {store_name}: {len(df_po)} позицій, "
        f"постачальників: {suppliers}, підсумок: {totals_text(df_po)}. "
        f"Топ: {top3_text(df_po)}"
    )

def compute_and_show(stock_path: str, suppliers_path: str):
    # Прокидуємо налаштування в модуль
    oe.OUT_DIR = out_dir or "out"
    os.makedirs(oe.OUT_DIR, exist_ok=True)
    oe.DRY_RUN = 1 if dry_run else 0
    oe.TELEGRAM_BOT_TOKEN = tg_token or ""
    oe.TELEGRAM_CHAT_ID = tg_chat or "555406850"

    # 1) Парсимо дані
    df_stock = oe.read_stock_excel(stock_path)
    if suppliers_path.lower().endswith((".xls", ".xlsx")):
        df_sup_raw = oe.read_excel_any(suppliers_path, header=0)
    else:
        df_sup_raw = pd.read_csv(suppliers_path)
    df_sup = oe.load_suppliers(df_sup_raw)

    # 2) Розрахунок
    po_a, po_b = oe.compute_orders(df_stock, df_sup)

    # 3) Зберегти CSV
    po_a_path = None
    po_b_path = None
    if not po_a.empty:
        po_a_path = os.path.join(oe.OUT_DIR, "PO_Боголюбова.csv")
        po_a.to_csv(po_a_path, index=False, encoding="utf-8-sig")
    if not po_b.empty:
        po_b_path = os.path.join(oe.OUT_DIR, "PO_Європейська_31а.csv")
        po_b.to_csv(po_b_path, index=False, encoding="utf-8-sig")

    # 4) Новий ПІДСУМОК (реальні дані)
    summary = f"{line_for_store(oe.STORE_A_NAME, po_a)}\n{line_for_store(oe.STORE_B_NAME, po_b)}"
    st.session_state.summary_text = summary

    st.success("Готово. Нижче — попередній перегляд і кнопки завантаження.")
    st.code(summary)

    # 5) Попередній перегляд і завантаження
    if po_a_path:
        st.download_button("⬇️ Завантажити PO_Боголюбова.csv",
                           data=open(po_a_path, "rb").read(),
                           file_name="PO_Боголюбова.csv", mime="text/csv")
        st.dataframe(po_a, use_container_width=True)
        st.session_state.po_a_path = po_a_path
    else:
        st.info("Для магазину Боголюбова замовлень немає.")

    if po_b_path:
        st.download_button("⬇️ Завантажити PO_Європейська_31а.csv",
                           data=open(po_b_path, "rb").read(),
                           file_name="PO_Європейська_31а.csv", mime="text/csv")
        st.dataframe(po_b, use_container_width=True)
        st.session_state.po_b_path = po_b_path
    else:
        st.info("Для магазину Європейська, 31а замовлень немає.")

# ---------- ACTIONS ----------
if btn_run:
    if not stock_file:
        st.error("Завантажте Excel із залишками.")
    elif not suppliers_file:
        st.error("Завантажте suppliers.csv/.xlsx.")
    else:
        try:
            stock_path = save_upload(stock_file, stock_file.name)
            suppliers_path = save_upload(suppliers_file, suppliers_file.name)
            compute_and_show(stock_path, suppliers_path)
        except Exception as e:
            st.exception(e)

if btn_send:
    if not st.session_state.summary_text:
        st.warning("Спершу натисніть «Розрахувати».")
    else:
        # Параметри надсилання (на випадок, якщо користувач змінить у сайдбарі)
        oe.DRY_RUN = 1 if dry_run else 0
        oe.TELEGRAM_BOT_TOKEN = tg_token or ""
        oe.TELEGRAM_CHAT_ID = tg_chat or "555406850"

        try:
            from order_engine import tg_send_message, tg_send_document
            tg_send_message(f"<b>AI Beer Stock Manager</b>\n{st.session_state.summary_text}")

            if st.session_state.po_a_path:
                tg_send_document(st.session_state.po_a_path, caption="Замовлення: <code>PO_Боголюбова.csv</code>")
            if st.session_state.po_b_path:
                tg_send_document(st.session_state.po_b_path, caption="Замовлення: <code>PO_Європейська_31а.csv</code>")

            if dry_run:
                st.info("DRY_RUN=1 — повідомлення тільки в логах сервера, до Telegram не відправляється.")
            else:
                st.success("Надіслано в Telegram.")
        except Exception as e:
            st.exception(e)
