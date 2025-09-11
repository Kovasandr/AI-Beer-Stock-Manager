# -*- coding: utf-8 -*-
"""
GitHub runner: тягне останній Excel з Gmail (export_limits), читає suppliers.csv з репо,
проганяє order_engine і надсилає у Telegram (DRY_RUN керується ENV).

Потрібні Secrets у GitHub:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
- GMAIL_USER
- GMAIL_APP_PASSWORD
Опційно:
- OUT_DIR (де зберігати CSV артефакти; за замовчуванням 'out')
- DRY_RUN (0/1)
"""
import os, re, io, imaplib, email, pathlib
import pandas as pd

# Імпортуємо локальний engine (лежить у корені репо)
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.resolve()))
import order_engine as oe

OUT_DIR = os.getenv("OUT_DIR", "out")
os.makedirs(OUT_DIR, exist_ok=True)

DRY_RUN = int(os.getenv("DRY_RUN", "0"))
oe.DRY_RUN = DRY_RUN
oe.OUT_DIR = OUT_DIR

oe.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
oe.TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "") or "555406850"

GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
SUBJ_CONTAINS = os.getenv("GMAIL_SUBJECT_CONTAINS", "export_limits")
FROM_CONTAINS = os.getenv("GMAIL_FROM_CONTAINS", "")

SUPPLIERS_PATH = os.getenv("SUPPLIERS_PATH", "suppliers.csv")  # з репо

def fetch_latest_excel_from_gmail(user, app_pwd, subj_contains="", from_contains=""):
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    M.login(user, app_pwd)
    M.select("INBOX")
    criteria = ['ALL']
    if subj_contains:
        criteria += ['SUBJECT', f'"{subj_contains}"']
    if from_contains:
        criteria += ['FROM', f'"{from_contains}"']
    rv, data = M.search(None, *criteria)
    if rv != 'OK':
        raise RuntimeError("IMAP search failed")
    ids = data[0].split()[::-1]
    saved_path = None
    info = None
    for num in ids[:50]:
        rv, msg_data = M.fetch(num, '(RFC822)')
        if rv != 'OK':
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        subject = email.header.decode_header(msg.get('Subject') or "")
        def decode(h):
            parts = []
            for s, enc in subject:
                if isinstance(s, bytes):
                    parts.append(s.decode(enc or 'utf-8', errors='ignore'))
                else:
                    parts.append(s)
            return ''.join(parts)
        subject_str = decode(subject)
        from_hdr = email.utils.parseaddr(msg.get('From'))[1]

        for part in msg.walk():
            if part.get_content_maintype() == 'multipart': continue
            if part.get('Content-Disposition') is None: continue
            filename = part.get_filename()
            if not filename: continue
            dh = email.header.decode_header(filename)
            fname = "".join([(t[0].decode(t[1] or 'utf-8') if isinstance(t[0], bytes) else str(t[0])) for t in dh])
            if not re.search(r'\.(xlsx|xls)$', fname, re.I):
                continue
            content = part.get_payload(decode=True)
            path = os.path.join(OUT_DIR, fname)
            with open(path, "wb") as f:
                f.write(content)
            saved_path = path
            info = f"FROM={from_hdr} SUBJECT={subject_str} FILE={fname}"
            if 'export_limits' in fname.lower():  # пріоритетне ім'я
                break
        if saved_path:
            break
    M.close()
    M.logout()
    if not saved_path:
        raise RuntimeError("Не знайдено вкладення .xlsx/.xls у жодному з останніх листів за фільтрами.")
    print("[GMAIL] Downloaded:", info)
    return saved_path

def main():
    # 1) стягуємо Excel з листа
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise SystemExit("GMAIL_USER/GMAIL_APP_PASSWORD не задані як Secrets.")
    stock_path = fetch_latest_excel_from_gmail(GMAIL_USER, GMAIL_APP_PASSWORD, SUBJ_CONTAINS, FROM_CONTAINS)

    # 2) suppliers
    if SUPPLIERS_PATH.lower().endswith((".xls",".xlsx")):
        sup_raw = oe.read_excel_any(SUPPLIERS_PATH, header=0)
    else:
        sup_raw = pd.read_csv(SUPPLIERS_PATH)
    df_sup = oe.load_suppliers(sup_raw)

    # 3) розрахунок
    df_stock = oe.read_stock_excel(stock_path)
    po_a, po_b = oe.compute_orders(df_stock, df_sup)

    # 4) збереження CSV (order_engine вже зберігає, але на всяк)
    if not po_a.empty:
        po_a.to_csv(os.path.join(OUT_DIR, "PO_Боголюбова.csv"), index=False, encoding="utf-8-sig")
    if not po_b.empty:
        po_b.to_csv(os.path.join(OUT_DIR, "PO_Європейська_31а.csv"), index=False, encoding="utf-8-sig")

    # 5) Telegram відправка
    summary = f"{oe.ai_comment(po_a, oe.STORE_A_NAME)}\n{oe.ai_comment(po_b, oe.STORE_B_NAME)}"
    print("[SUMMARY]\n", summary)
    from order_engine import tg_send_message, tg_send_document
    tg_send_message(f"<b>AI Beer Stock Manager</b>\n{summary}")
    if not po_a.empty:
        tg_send_document(os.path.join(OUT_DIR, "PO_Боголюбова.csv"), caption="Замовлення: <code>PO_Боголюбова.csv</code>")
    if not po_b.empty:
        tg_send_document(os.path.join(OUT_DIR, "PO_Європейська_31а.csv"), caption="Замовлення: <code>PO_Європейська_31а.csv</code>")

if __name__ == "__main__":
    main()
