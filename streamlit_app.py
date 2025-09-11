# streamlit_app.py
import os
import pandas as pd
import streamlit as st
from app.stock_manager import build_purchase_order
from app.mailer import send_mail, build_html
from app.email_fetcher import fetch_inventory_from_email
import requests

st.set_page_config(page_title="AI Beer Stock Manager", layout="wide")
st.title("🍺 AI Beer Stock Manager")

# === Налаштування середовища ===
SUPPLIER_EMAIL = os.getenv("SUPPLIER_EMAIL", "")
DRY_RUN = (os.getenv("DRY_RUN", "1").strip() == "1")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def tg_notify(text: str):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                          json={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        except Exception:
            pass

# === UI: завантаження файлів ===
st.sidebar.header("Вхідні дані (локальний тест)")
sales_file = st.sidebar.file_uploader("sales.csv (date, sku, qty)", type=["csv"])
inventory_file = st.sidebar.file_uploader("inventory.csv (sku, name, stock)", type=["csv"])

colA, colB, colC = st.columns(3)
with colA:
    load_from_email = st.button("📥 Підтягнути інвентар з пошти (Excel)")
with colB:
    calc_btn = st.button("🧮 Розрахувати замовлення")
with colC:
    send_btn = st.button("✉️ Надіслати замовлення постачальнику")

status = st.empty()
po_df = None
summary_text = ""

# === Крок 1: отримати інвентар (або з UI, або з пошти) ===
inv_path = "sample_data/inventory.csv"  # дефолтний шлях, куди писатимемо
sales_path = "sample_data/sales.csv"    # як і раніше

if load_from_email:
    try:
        inv_df = fetch_inventory_from_email(inv_path)
        status.success(f"✅ Інвентар завантажено з пошти та збережено у {inv_path}. Рядків: {len(inv_df)}")
        st.dataframe(inv_df.head(20), use_container_width=True)
    except Exception as e:
        status.error(f"❌ Не вдалося підтягнути інвентар із пошти: {e}")

# Якщо користувач завантажив локальні файли — зберігаємо тимчасово і використовуємо їх
if sales_file is not None:
    tmp_sales = "tmp_sales.csv"
    with open(tmp_sales, "wb") as f:
        f.write(sales_file.read())
    sales_path = tmp_sales

if inventory_file is not None:
    tmp_inv = "tmp_inventory.csv"
    with open(tmp_inv, "wb") as f:
        f.write(inventory_file.read())
    inv_path = tmp_inv

# === Крок 2: розрахунок PO ===
if calc_btn:
    try:
        po_df, summary_text = build_purchase_order(sales_path, inv_path)
        st.subheader("🔎 Підсумок")
        st.code(summary_text)
        st.subheader("📦 Purchase Order")
        st.dataframe(po_df, use_container_width=True)
        if po_df is None or po_df.empty:
            status.info("Замовлень немає — запас достатній.")
        else:
            status.success("✅ Розрахунок виконано.")
    except Exception as e:
        status.error(f"❌ Помилка розрахунку: {e}")

# === Крок 3: відправка листа ===
if send_btn:
    try:
        # Якщо PO ще не рахували в цій сесії — перерахуємо
        if po_df is None:
            po_df, summary_text = build_purchase_order(sales_path, inv_path)

        subject = "Замовлення на поповнення запасів (AI Beer Stock Manager)"
        to_email = SUPPLIER_EMAIL or "kovalenko55555@gmail.com"

        result = send_mail(po_df, subject=subject, to_email=to_email, dry_run=DRY_RUN)
        html_preview = result.get("preview_html", build_html(po_df, subject))

        st.subheader("📧 Прев’ю листа")
        st.markdown(html_preview, unsafe_allow_html=True)

        if result.get("sent"):
            status.success(f"✅ Лист відправлено на {to_email}")
            tg_notify("✅ Замовлення відправлено постачальнику (див. пошту).")
        else:
            status.warning("ℹ️ DRY_RUN або немає SMTP-конфігурації — показано прев’ю без відправки.")
            tg_notify("ℹ️ Прев’ю замовлення згенеровано (DRY_RUN).")

    except Exception as e:
        status.error(f"❌ Помилка відправки: {e}")
