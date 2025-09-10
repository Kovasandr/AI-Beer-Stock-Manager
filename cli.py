import argparse
import os
from dotenv import load_dotenv

from app.stock_manager import build_purchase_order
from app.ai_layer import generate_supplier_message
from app.emailer import send_email


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="AI Beer Stock Manager CLI")
    parser.add_argument("--sales", required=True, help="Path to sales CSV")
    parser.add_argument("--inventory", required=True, help="Path to inventory CSV")
    parser.add_argument("--supplier-email", required=False, default=os.getenv("SUPPLIER_EMAIL", ""))
    args = parser.parse_args()

    # 1) Розрахунок потреби та формування PO-таблиці
    po_df, summary = build_purchase_order(args.sales, args.inventory)

    # 2) AI-генерація “людяного” повідомлення постачальнику
    #    (якщо OPENAI_API_KEY не заданий або станеться помилка – повернемо простий текст)
    try:
        ai_message = generate_supplier_message(po_df)
    except Exception as e:
        ai_message = (
            "Прим
