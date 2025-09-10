import os
import datetime as dt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from app.stock_manager import build_purchase_order
from app.emailer import send_email

# Спроба підключити AI-пояснення (не обовʼязково для демо)
try:
    from app.ai_layer import generate_supplier_message
    HAS_AI = True
except Exception:
    HAS_AI = False

load_dotenv()
st.set_page_config(page_title="🍺 AI Beer Stock Manager – Майстер", layout="wide")
st.title("🍺 AI Beer Stock Manager — Чат-майстер")

st.markdown(
    "Виберіть дію, вкажіть джерело даних (завантажте CSV або оберіть інше джерело), "
    "і натисніть **Запустити**. Система все порахує автоматично."
)

# --------- КРОК 1: ЩО ЗРОБИТИ?
task = st.radio(
    "Що потрібно зробити?",
    ["Автозамовлення", "Прогноз на свята"],
    horizontal=True,
)

# --------- КРОК 2: ЗВІДКИ ДАНІ?
source = st.radio(
    "Звідки беремо дані?",
    ["Завантажити CSV (просто)", "Gmail (скоро)", "Google Sheets (скоро)"],
    help="Для демо достатньо завантажити CSV із продажами й (за потреби) інвентарем."
)

# Поля для Email-одержувача
default_email = os.getenv("SUPPLIER_EMAIL", "")
report_email = st.text_input(
    "Куди надіслати результат (email)?",
    value=default_email,
    help="Можна вказати свою пошту для тесту. DRY_RUN=1 друкує лист у лог замість відправки."
)

# --------- Ввід файлів для простого джерела
sales_path = inv_path = None
if source.startswith("Завантажити"):
    st.subheader("Завантаження файлів")
    sales_file = st.file_uploader("Продажі (sales.csv) — колонки: date, sku, qty", type=["csv"])
    inv_file = None
    if task == "Автозамовлення":
        inv_file = st.file_uploader("Інвентар (inventory.csv) — колонки: sku, name, stock, ...", type=["csv"])

    # Збережемо тимчасово
    import tempfile
    if sales_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as sf:
            sf.write(sales_file.read())
            sales_path = sf.name
    if inv_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as inf:
            inf.write(inv_file.read())
            inv_path = inf.name

# --------- Налаштування для ПРОГНОЗУ НА СВЯТА
holiday_date = None
holiday_boost = 0.0
if task == "Прогноз на свята":
    col1, col2 = st.columns(2)
    with col1:
        holiday_date = st.date_input("Дата свята", value=dt.date.today() + dt.timedelta(days=7))
    with col2:
        holiday_boost = st.slider("Очікуване зростання попиту на свято, %", 0, 200, 30) / 100.0

    st.caption("Простий підхід: беремо середній попит за днями тижня та додаємо коефіцієнт на день свята.")

def forecast_next_7_days(sales_csv: str, holiday_dt: dt.date, boost: float) -> pd.DataFrame:
    """Наївний прогноз: середній попит по днях тижня + підсилення на день свята."""
    df = pd.read_csv(sales_csv, parse_dates=["date"])
    df["dow"] = df["date"].dt.dayofweek
    # середній продаж за днями тижня для кожного SKU
    avg = df.groupby(["sku", "dow"])["qty"].mean().rename("avg_qty").reset_index()

    horizon = [dt.date.today() + dt.timedelta(days=i) for i in range(7)]
    rows = []
    for d in horizon:
        dow = d.weekday()
        day_avg = avg[avg["dow"] == dow][["sku", "avg_qty"]].copy()
        day_avg["date"] = d
        if holiday_dt == d:
            day_avg["avg_qty"] = (day_avg["avg_qty"] * (1.0 + boost)).round(2)
        rows.append(day_avg)
    out = pd.concat(rows).fillna({"avg_qty": 0})
    return out[["date", "sku", "avg_qty"]].rename(columns={"avg_qty": "forecast_qty"})

run = st.button("🚀 Запустити")

if run:
    if not sales_path:
        st.error("Будь ласка, надайте дані про продажі (sales.csv).")
        st.stop()

    if task == "Автозамовлення":
        if not inv_path:
            st.error("Для автозамовлення потрібен ще inventory.csv.")
            st.stop()

        po_df, summary = build_purchase_order(sales_path, inv_path)
        st.subheader("Підсумок")
        st.code(summary["report_text"], language="markdown")
        st.subheader("Позиції до замовлення")
        st.dataframe(po_df, use_container_width=True)

        # Формування тіла листа: звіт + (опційно) AI-пояснення
        ai_text = ""
        if HAS_AI:
            try:
                ai_text = "\n\n" + generate_supplier_message(po_df)
            except Exception as e:
                ai_text = f"\n\nПримітка: AI-пояснення тимчасово недоступне. Технічна довідка: {e}"

        if st.button("✉️ Надіслати постачальнику"):
            subject = f"PO: Автозамовлення {summary['date']} (поз. {len(po_df)})"
            body = summary["report_text"] + ai_text
            send_email(subject=subject, body=body, to_email=report_email, po_df=po_df)
            st.success("Готово! Перевірте пошту (або логи, якщо DRY_RUN=1).")

    else:  # Прогноз на свята
        fc_df = forecast_next_7_days(sales_path, holiday_date, holiday_boost)
        st.subheader("Прогноз на 7 днів")
        st.dataframe(fc_df, use_container_width=True)

        # Зведення по SKU на день свята
        day_fc = fc_df[fc_df["date"] == pd.Timestamp(holiday_date)]
        lines = [f"Прогноз на {holiday_date} (boost {int(holiday_boost*100)}%):"]
        for r in day_fc.itertuples():
            lines.append(f"- {r.sku}: {r.forecast_qty:.1f} шт.")
        summary_text = "\n".join(lines)
        st.code(summary_text, language="markdown")

        if st.button("✉️ Надіслати прогноз на email"):
            subject = f"Прогноз продажів на свято {holiday_date}"
            body = summary_text
            # Прикріпимо увесь 7-денний прогноз як CSV
            send_email(subject=subject, body=body, to_email=report_email, po_df=fc_df.rename(columns={"forecast_qty":"qty"}))
            st.success("Прогноз надіслано (або надруковано в лог, якщо DRY_RUN=1).")

st.divider()
st.caption("Джерела: зараз — CSV. Далі підключимо Gmail/Sheets, щоб нічого не завантажувати вручну.")
