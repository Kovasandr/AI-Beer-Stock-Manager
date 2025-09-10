import argparse
import os
from dotenv import load_dotenv

from app.stock_manager import build_purchase_order
from app.ai_layer import generate_supplier_message
from app.emailer import send_email

load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="AI Beer Stock Manager CLI")
    parser.add_argument("--sales", required=True, help="Path to sales CSV")
    parser.add_argument("--inventory", required=True, help="Path to inventory CSV")
    parser.add_argument("--supplier-email", required=False, default=os.getenv("SUPPLIER_EMAIL", ""))
    args = parser.parse_args()

    po_df, summary = build_purchase_order(args.sales, args.inventory)

    subject = f"PO: Автозамовлення {summary['date']} (поз. {len(po_df)})"
    body = summary["report_text"]
    to_email = args.supplier_email or os.getenv("SUPPLIER_EMAIL")

    send_email(subject=subject, body=body, to_email=to_email, po_df=po_df)

if __name__ == "__main__":
    main()
