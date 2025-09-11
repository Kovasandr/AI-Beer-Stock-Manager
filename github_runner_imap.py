# -*- coding: utf-8 -*-
# IMAP → XLSX → Telegram + Missing suppliers summary
import os, re, io, imaplib, email, pathlib, pandas as pd, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.resolve()))
import order_engine as oe

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "")
IMAP_FOLDER = os.getenv("IMAP_FOLDER", "INBOX")
IMAP_FILENAME_REGEX = os.getenv("IMAP_FILENAME_REGEX", r"export_limits.*\.(xlsx|xls)$")

oe.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
oe.TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
oe.DRY_RUN = int(os.getenv("DRY_RUN", "0"))
oe.OUT_DIR = os.getenv("OUT_DIR", "out")
SUPPLIERS_PATH = os.getenv("SUPPLIERS_PATH", "suppliers.csv")
os.makedirs(oe.OUT_DIR, exist_ok=True)

def fetch_latest_attachment():
    regex = re.compile(IMAP_FILENAME_REGEX, re.I)
    M = imaplib.IMAP4_SSL(IMAP_HOST, 993); M.login(IMAP_USER, IMAP_PASSWORD)
    typ,_ = M.select(IMAP_FOLDER)
    if typ != "OK": raise RuntimeError(f"IMAP: не вдалось відкрити {IMAP_FOLDER}")
    typ, data = M.search(None, "ALL")
    if typ != "OK": raise RuntimeError("IMAP: search failed")
    ids = data[0].split()[::-1]
    for num in ids[:80]:
        typ, msg_data = M.fetch(num, "(RFC822)")
        if typ != "OK": continue
        msg = email.message_from_bytes(msg_data[0][1])
        for part in msg.walk():
            if part.get_content_maintype()=="multipart": continue
            if part.get("Content-Disposition") is None: continue
            raw = part.get_filename()
            if not raw: continue
            dh = email.header.decode_header(raw)
            fname = "".join([(t[0].decode(t[1] or 'utf-8') if isinstance(t[0],bytes) else str(t[0])) for t in dh])
            if not regex.search(fname): continue
            path = os.path.join(oe.OUT_DIR, fname)
            with open(path,"wb") as f: f.write(part.get_payload(decode=True))
            M.close(); M.logout(); print("[IMAP] Downloaded:", fname); return path
    M.close(); M.logout(); raise RuntimeError(f"IMAP: не знайдено вкладення за regex {IMAP_FILENAME_REGEX}")

def fmt(x):
    xf = float(x)
    return f"{int(xf)}" if xf.is_integer() else f"{xf:.2f}"

def totals_text(df: pd.DataFrame) -> str:
    if df.empty: return "0"
    sums = df.groupby("Одиниця")["Замовити"].sum()
    pref = ["л","кг","шт"]
    parts = [f"{fmt(sums[u])} {u}" for u in pref if u in sums and sums[u] > 0]
    parts += [f"{fmt(v)} {u}" for u,v in sums.items() if u not in pref and v > 0]
    return ", ".join(parts) if parts else "0"

def line_for_store(name: str, df_po: pd.DataFrame) -> str:
    supp = df_po["Постачальник"].nunique() if not df_po.empty else 0
    return f"Магазин {name}: {len(df_po)} позицій, постачальників: {supp}, підсумок: {totals_text(df_po)}."

def main():
    stock_path = fetch_latest_attachment()
    sup_raw = oe.read_excel_any(SUPPLIERS_PATH, header=0) if SUPPLIERS_PATH.lower().endswith((".xls",".xlsx")) else pd.read_csv(SUPPLIERS_PATH)
    df_sup = oe.load_suppliers(sup_raw)
    df_stock = oe.read_stock_excel(stock_path)
    po_a, po_b, missing = oe.compute_orders_and_missing(df_stock, df_sup)

    # Save XLSX
    if not po_a.empty:
        oe.save_xlsx(po_a, os.path.join(oe.OUT_DIR, "PO_Боголюбова.xlsx"))
    if not po_b.empty:
        oe.save_xlsx(po_b, os.path.join(oe.OUT_DIR, "PO_Європейська_31а.xlsx"))
    if not missing.empty:
        oe.save_xlsx(missing, os.path.join(oe.OUT_DIR, "MISSING_SUPPLIERS.xlsx"))

    # Summary (реальні дані)
    summary = f"{line_for_store(oe.STORE_A_NAME, po_a)}\n{line_for_store(oe.STORE_B_NAME, po_b)}"
    print("[SUMMARY]\n", summary)

    # Send to Telegram
    from order_engine import tg_send_message, tg_send_document
    tg_send_message(f"<b>AI Beer Stock Manager</b>\n{summary}")
    for fname in ["PO_Боголюбова.xlsx","PO_Європейська_31а.xlsx","MISSING_SUPPLIERS.xlsx"]:
        p = os.path.join(oe.OUT_DIR, fname)
        if os.path.exists(p):
            tg_send_document(p, caption=f"<code>{fname}</code>")

if __name__ == "__main__":
    main()
