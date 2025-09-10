import os, io, requests
import pandas as pd

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        print("[WARN] TELEGRAM not configured: skip")
        return
    r = requests.post(f"{API_URL}/sendMessage", data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})
    print("[TG]", r.status_code, r.text[:200])

def send_table(po_df: pd.DataFrame, caption: str = "PO.csv"):
    if not BOT_TOKEN or not CHAT_ID:
        return
    buf = io.BytesIO()
    po_df.to_csv(buf, index=False)
    buf.seek(0)
    files = {"document": ("PO.csv", buf, "text/csv")}
    data = {"chat_id": CHAT_ID, "caption": caption}
    r = requests.post(f"{API_URL}/sendDocument", data=data, files=files)
    print("[TG-DOC]", r.status_code, r.text[:200])
