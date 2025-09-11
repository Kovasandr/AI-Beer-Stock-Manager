# app/email_fetcher.py
import imaplib
import email
import re
import io
import os
import pandas as pd

def _open_mailbox(host, user, password, folder):
    M = imaplib.IMAP4_SSL(host)
    M.login(user, password)
    M.select(folder)
    return M

def _search_msgs(M, filename_regex=None):
    status, data = M.search(None, "ALL")
    if status != "OK":
        return []
    ids = data[0].split()
    out = []
    for msg_id in reversed(ids):  # newest first
        status, msg_data = M.fetch(msg_id, "(RFC822)")
        if status != "OK":
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                fname = part.get_filename() or ""
                if filename_regex and not re.search(filename_regex, fname, re.IGNORECASE):
                    continue
                out.append((msg_id, msg, fname, part))
    return out

def _read_excel_bytes(b: bytes) -> pd.DataFrame:
    # Читаємо .xls/.xlsx
    with io.BytesIO(b) as bio:
        xls = pd.ExcelFile(bio)
        sheet = xls.sheet_names[0]
        df = pd.read_excel(bio, sheet_name=sheet)
    return df

def _parse_export_limits(df: pd.DataFrame) -> pd.DataFrame:
    """
    Очікуваний формат (з прикладу export_limits.xls):
    Перший рядок містить заголовки у клітинках:
      'Інгредієнти', 'Категорія', ... 'Загальний залишок', 'Ліміт'
    Подальші рядки — дані. Нам потрібні колонки: sku/name, stock, limit.
    """
    # Підтягуємо хедер з першого рядка
    header = df.iloc[0].tolist()
    df = df.iloc[1:].copy()
    df.columns = header
    # Переіменуємо у зрозумілі ключі
    rename_map = {}
    for c in df.columns:
        c2 = str(c).strip()
        if c2.lower().startswith("інгредієнти"):
            rename_map[c] = "name"
        elif c2.lower().startswith("загальний залишок"):
            rename_map[c] = "total"
        elif c2.lower().startswith("ліміт"):
            rename_map[c] = "limit"
    df = df.rename(columns=rename_map)

    # Фільтруємо тільки рядки, де є назва
    df = df[df.get("name").notna()].copy()

    def _to_number(x):
        if pd.isna(x):
            return 0.0
        s = str(x)
        # Витягуємо число, десяткові — з крапкою/комою
        m = re.findall(r"[\d]+(?:[.,]\d+)?", s)
        if not m:
            return 0.0
        v = m[0].replace(",", ".")
        try:
            return float(v)
        except:
            return 0.0

    df["stock"] = df.get("total", 0).apply(_to_number)
    df["limit_val"] = df.get("limit", 0).apply(_to_number)
    df["sku"] = df["name"].astype(str)  # якщо немає окремого SKU — використовуємо name

    out = df[["sku", "name", "stock", "limit_val"]].copy()
    out = out.fillna({"stock": 0, "limit_val": 0})
    return out

def fetch_inventory_from_email(out_csv_path: str) -> pd.DataFrame:
    host = os.getenv("IMAP_HOST", "")
    user = os.getenv("IMAP_USER", "")
    password = os.getenv("IMAP_PASSWORD", "")
    folder = os.getenv("IMAP_FOLDER", "INBOX")
    filename_regex = os.getenv("IMAP_FILENAME_REGEX", r".*limits.*\.(xls|xlsx)")

    M = _open_mailbox(host, user, password, folder)
    try:
        attachments = _search_msgs(M, filename_regex=filename_regex)
        if not attachments:
            raise RuntimeError("Не знайдено відповідних вкладень з лімітами/залишками.")
        # беремо найсвіжіше
        _, msg, fname, part = attachments[0]
        data = part.get_payload(decode=True)
        raw_df = _read_excel_bytes(data)
        inv_df = _parse_export_limits(raw_df)

        # зберігаємо нормалізований інвентар у UTF-8
        inv_df.to_csv(out_csv_path, index=False, encoding="utf-8")
        return inv_df
    finally:
        try:
            M.close()
            M.logout()
        except Exception:
            pass
