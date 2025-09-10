import argparse
import os
from dotenv import load_dotenv

from app.stock_manager import build_purchase_order
from app.ai_layer import generate_supplier_message
from app.emailer import send_email
from app.telegram_notify import send_message, send_table


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
    try:
        ai_message = generate_supplier_message(po_df)
    except Exception as e:
        ai_message = "Примітка: AI-пояснення тимчасово недоступне. Технічна довідка: " + str(e)

    # 3) Формуємо тему та тіло листа (звіт + AI-пояснення)
    subject = f"PO: Автозамовлення {summary['date']} (поз. {len(po_df)})"
    body = summary["report_text"] + "\n\n" + ai_message

    # 4) Кому надсилати
    to_email = args.supplier_email or os.getenv("SUPPLIER_EMAIL")

    # 5) Надсилання email (або DRY RUN — друк у лог)
    send_email(subject=subject, body=body, to_email=to_email, po_df=po_df)

    # 6) Telegram-сповіщення (спрацює, якщо задані TELEGRAM_BOT_TOKEN і TELEGRAM_CHAT_ID)
    preview = subject + "\n" + summary["report_text"].splitlines()[0]
    send_message(preview)
    send_table(po_df, caption=subject)


if __name__ == "__main__":
    main()
