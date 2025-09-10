import os
import streamlit as st
from dotenv import load_dotenv
from app.stock_manager import build_purchase_order
from app.emailer import send_email

load_dotenv()

st.set_page_config(page_title="AI Beer Stock Manager", layout="wide")
st.title("🍺 AI Beer Stock Manager")

st.write("Завантажте CSV з продажами та інвентарем, і система згенерує замовлення.")

sales_file = st.file_uploader("sales.csv", type=["csv"])
inv_file = st.file_uploader("inventory.csv", type=["csv"])

if st.button("Розрахувати замовлення") and sales_file and inv_file:
    import pandas as pd
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as sf:
        sf.write(sales_file.read())
        sales_path = sf.name

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as inf:
        inf.write(inv_file.read())
        inv_path = inf.name

    po_df, summary = build_purchase_order(sales_path, inv_path)
    st.subheader("Підсумок")
    st.write(summary["report_text"])
    st.subheader("PO (таблиця)")
    st.dataframe(po_df)

    if st.button("Надіслати постачальнику (email)"):
        to_email = st.text_input("Email постачальника", os.getenv("SUPPLIER_EMAIL", ""))
        if to_email:
            send_email(subject=f"PO {summary['date']}", body=summary["report_text"], to_email=to_email, po_df=po_df)
            st.success("Відправлено (або надруковано, якщо DRY_RUN=1). Перевірте логи.")
        else:
            st.warning("Вкажіть email постачальника.")