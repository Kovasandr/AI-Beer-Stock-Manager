# github_runner_imap.py
# -*- coding: utf-8 -*-
import os, re, io, imaplib, email, pathlib, pandas as pd, sys

# Підтягуємо локальний order_engine.py (лежить у корені)
sys.path.insert(0, str(pathlib.Path(__file__).parent.resolve()))
import order_engine as oe  # ваш двигун (TG-відправка вже всередині)

# ===== Secrets / Env =====
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
    M = imaplib.IMAP4_SSL(IMAP_HOST, 993)
    M.login(IMAP_USER, IMAP_PASSWORD)
    typ, _ = M.select(IMAP_FOLDER)
    if typ != "OK":
        raise RuntimeError(f"IMAP: не вдалось відкрити папку {IMAP_FOLDER}")
    typ, data = M.search(None, "ALL")
    if typ != "OK":
        raise RuntimeError("IMAP: search failed")
    ids = data[0].split()[::-1]  # latest first
    for num in ids[:80]:
        typ, msg_data = M.fetch(num, "(RFC822)")
        if typ != "OK":
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                continue
            raw_name = part.get_filename()
            if not raw_name:
                continue
            dh = email.header.decode_header(raw_name)
            fname = "".join([(t[0].decode(t[1] or "utf-8") if isinstance(t[0], bytes) else str(t[0])) for t in dh])
            if not regex.search(fname):
                continue
            path = os.path.join(oe.OUT_DIR, fname)
            with open(path, "wb") as f:
                f.write(part.get_payload(decode=True))
            M.close(); M.logout()
            print("[IMAP] Downloaded:", fname)
            return path
    M.close(); M.logout()
    raise RuntimeError(f"IMAP: не знайдено вкладення за regex {IMAP_FILENAME_REGEX}")

def fmt_num(x: float) -> str:
    return f"{int(x)}" if float(x).is_integer() else f"{x:.2f}"

def totals_text(df_po: pd.DataFrame) -> str:
    """Повертає текст підсумку виду '125 л, 18 кг, 47 шт' для конкретного PO."""
    if df_po.empty:
        return "0"
    # заміна None на 'шт' на всяк випадок
    units = df_po["unit"].fillna("шт")
    sums = df_po.assign(unit=units).groupby("unit", dropna=False)["order_qty"].sum()
    order = ["л", "кг", "шт"]
    parts = []
    for u in order:
        if u in sums and sums[u] > 0:
            parts.append(f"{fmt_num(sums[u])} {u}")
    # якщо були інші одиниці — теж покажемо
    for u, v in sums.items():
        if u not in order and v > 0:
            parts.append(f"{fmt_num(v)} {u}")
    return ", ".join(parts) if parts else "0"

def top3(df_po: pd.DataFrame) -> str:
    if df_po.empty:
        return "—"
    x = df_po.sort_values("order_qty", ascending=False).head(3)
    return ", ".join(
        f"{r.product_name} — {fmt_num(r.order_qty)} {r.unit}" for r in x.itertuples()
    )

def line_for_store(store_name: str, df_po: pd.DataFrame) -> str:
    suppliers = df_po["supplier_name"].nunique() if not df_po.empty else 0
    return (
        f"Магазин {store_name}: {len(df_po)} позицій, постачальників: {suppliers}, "
        f"підсумок: {totals_text(df_po)}. Топ: {top3(df_po)}"
    )

def main():
    stock_path = fetch_latest_attachment()

    # suppliers
    if SUPPLIERS_PATH.lower().endswith((".xls", ".xlsx")):
        df_sup_raw = oe.read_excel_any(SUPPLIERS_PATH, header=0)
    else:
        df_sup_raw = pd.read_csv(SUPPLIERS_PATH)
    df_sup = oe.load_suppliers(df_sup_raw)

    # compute
    df_stock = oe.read_stock_excel(stock_path)
    po_a, po_b = oe.compute_orders(df_stock, df_sup)

    # save CSV
    if not po_a.empty:
        po_a.to_csv(os.path.join(oe.OUT_DIR, "PO_Боголюбова.csv"), index=False, encoding="utf-8-sig")
    if not po_b.empty:
        po_b.to_csv(os.path.join(oe.OUT_DIR, "PO_Європейська_31а.csv"), index=False, encoding="utf-8-sig")

    # summary (реальні дані)
    summary = f"{line_for_store(oe.STORE_A_NAME, po_a)}\n{line_for_store(oe.STORE_B_NAME, po_b)}"
    print("[SUMMARY]\n", summary)

    # Telegram
    from order_engine import tg_send_message, tg_send_document
    tg_send_message(f"<b>AI Beer Stock Manager</b>\n{summary}")
    if not po_a.empty:
        tg_send_document(os.path.join(oe.OUT_DIR, "PO_Боголюбова.csv"), caption="Замовлення: <code>PO_Боголюбова.csv</code>")
    if not po_b.empty:
        tg_send_document(os.path.join(oe.OUT_DIR, "PO_Європейська_31а.csv"), caption="Замовлення: <code>PO_Європейська_31а.csv</code>")

if __name__ == "__main__":
    main()
