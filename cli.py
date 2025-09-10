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
    #    Якщо OPENAI_API_KEY не заданий або сталася помилка — підставляємо коротку примітку
    try:
        ai_message = generate_supplier_message(po_df)
    except Exception as e:
        ai_message = "Примітка: AI-пояснення тимчасово недоступне. Технічна довідка: " + str(e)

    # 3) Формуємо тему та тіло листа (звіт + AI-пояснення)
    subject = f"PO: Автозамовлення {summary['date']} (поз. {len(po_df)})"
    body = summary["report_text"] + "\n\n" + ai_message

    # 4) Кому надсилати
    to_email = args.supplier_email or os.getenv("SUPPLIER_EMAIL")

    # 5) Надсилання (або DRY RUN — друк у лог)
    send_email(subject=subject, body=body, to_email=to_email, po_df=po_df)


if __name__ == "__main__":
    main()
