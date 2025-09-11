# -*- coding: utf-8 -*-
import os, tempfile, pandas as pd, streamlit as st
import order_engine as oe

st.set_page_config(page_title="AI Beer Stock Manager", page_icon="🍺", layout="wide")
st.title("🍺 AI Beer Stock Manager — Streamlit (XLSX)")
st.caption("Експорт .xlsx у зрозумілому вигляді + список товарів без постачальника")

with st.sidebar:
    st.header("⚙️ Налаштування")
    out_dir = st.text_input("Папка для XLSX (OUT_DIR)", value=os.getenv("OUT_DIR", "out"))
    dry_run = st.checkbox("DRY_RUN (тільки локально, без TG)", value=True)
    tg_token = st.text_input("TELEGRAM_BOT_TOKEN", value=os.getenv("TELEGRAM_BOT_TOKEN", ""), type="password")
    tg_chat  = st.text_input("TELEGRAM_CHAT_ID", value=os.getenv("TELEGRAM_CHAT_ID", "555406850"))

st.subheader("1) Вхідні файли")
c1, c2 = st.columns(2)
with c1:
    stock_file = st.file_uploader("Excel із залишками (export_limits.xlsx / .xls)", type=["xlsx","xls"])
with c2:
    suppliers_file = st.file_uploader("suppliers.csv або .xlsx/.xls", type=["csv","xlsx","xls"])

col_run, col_send = st.columns(2)
btn_run = col_run.button("🔢 Розрахувати")
btn_send = col_send.button("🚀 Надіслати в Telegram")

tmp_dir = tempfile.mkdtemp(prefix="beer_streamlit_")

def save_upload(f, name):
    path = os.path.join(tmp_dir, name)
    with open(path, "wb") as fh: fh.write(f.read())
    return path

if "paths" not in st.session_state:
    st.session_state.paths = {}

def compute_and_show(stock_path, suppliers_path):
    oe.OUT_DIR = out_dir or "out"; os.makedirs(oe.OUT_DIR, exist_ok=True)
    oe.DRY_RUN = 1 if dry_run else 0
    oe.TELEGRAM_BOT_TOKEN = tg_token or ""
    oe.TELEGRAM_CHAT_ID = tg_chat or "555406850"

    po_a, po_b, missing = oe.process_and_send(stock_path, suppliers_path)  # зберігає та (якщо DRY_RUN=0) шле у TG
    st.success("Готово. Файли сформовані у OUT_DIR. Попередній перегляд нижче.")

    if not po_a.empty:
        st.subheader("PO — Боголюбова")
        st.dataframe(po_a, use_container_width=True)
        xlsx_a = os.path.join(oe.OUT_DIR, "PO_Боголюбова.xlsx")
        st.download_button("⬇️ Завантажити PO_Боголюбова.xlsx", data=open(xlsx_a, "rb").read(),
                           file_name="PO_Боголюбова.xlsx")
        st.session_state.paths["a"] = xlsx_a
    else:
        st.info("Для магазину Боголюбова замовлень немає.")

    if not po_b.empty:
        st.subheader("PO — Європейська, 31а")
        st.dataframe(po_b, use_container_width=True)
        xlsx_b = os.path.join(oe.OUT_DIR, "PO_Європейська_31а.xlsx")
        st.download_button("⬇️ Завантажити PO_Європейська_31а.xlsx", data=open(xlsx_b, "rb").read(),
                           file_name="PO_Європейська_31а.xlsx")
        st.session_state.paths["b"] = xlsx_b
    else:
        st.info("Для магазину Європейська, 31а замовлень немає.")

    st.subheader("Товари без постачальника")
    if missing.empty:
        st.success("Всі товари мають постачальника ✅")
    else:
        st.warning("Є товари без постачальника — доповніть у suppliers.csv")
        st.dataframe(missing, use_container_width=True)
        xlsx_m = os.path.join(oe.OUT_DIR, "MISSING_SUPPLIERS.xlsx")
        st.download_button("⬇️ Завантажити MISSING_SUPPLIERS.xlsx", data=open(xlsx_m, "rb").read(),
                           file_name="MISSING_SUPPLIERS.xlsx")
        st.session_state.paths["m"] = xlsx_m

if btn_run:
    if not stock_file:
        st.error("Завантажте Excel із залишками.")
    elif not suppliers_file:
        st.error("Завантажте suppliers.csv/.xlsx.")
    else:
        stock_path = save_upload(stock_file, stock_file.name)
        suppliers_path = save_upload(suppliers_file, suppliers_file.name)
        try:
            compute_and_show(stock_path, suppliers_path)
        except Exception as e:
            st.exception(e)

if btn_send:
    if not st.session_state.get("paths"):
        st.warning("Спершу натисніть «Розрахувати».")
    else:
        oe.DRY_RUN = 1 if dry_run else 0
        oe.TELEGRAM_BOT_TOKEN = tg_token or ""
        oe.TELEGRAM_CHAT_ID = tg_chat or "555406850"
        from order_engine import tg_send_message, tg_send_document
        tg_send_message("<b>AI Beer Stock Manager</b>\nВідправлення сформованих XLSX.")
        for key in ["a", "b", "m"]:
            p = st.session_state.paths.get(key)
            if p and os.path.exists(p):
                tg_send_document(p, caption=f"<code>{os.path.basename(p)}</code>")
        if dry_run:
            st.info("DRY_RUN=1 — надсилання лише у логах.")
        else:
            st.success("Відправлено в Telegram.")
