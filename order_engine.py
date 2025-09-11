# -*- coding: utf-8 -*-
"""
AI Beer Stock Manager — дві точки (Боголюбова / Європейська, 31а) з відправкою в Telegram

Функціонал:
- Читає Excel із залишками (терпить шапку, знаходить заголовки)
- Парсить кількість та одиниці (шт/л/кг)
- Ділить Ліміт навпіл для кожного магазину (ceil)
- Рахує потребу окремо по магазинах, округляє до pack_size з suppliers
- Зберігає 2 CSV у OUT_DIR
- Надсилає підсумок + обидва CSV у Telegram (sendMessage + sendDocument)
- DRY_RUN=1 => тільки локальне збереження і друк у консоль (без надсилання)

ENV (у .env):
- DRY_RUN=1|0
- OUT_DIR=out
- TELEGRAM_BOT_TOKEN=123456:ABC...   # ваш токен ботa
- TELEGRAM_CHAT_ID=555406850         # ваш chat_id (за замовчуванням 555406850)
- RECIPIENT_EMAIL=... (залишено для сумісності, не обов'язково)
"""
import os, io, re, math, ssl, unicodedata, json, requests
import pandas as pd
from email.message import EmailMessage  # сумісність; email відправка наразі не використовується
import smtplib

# --------- env loader ---------
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# =====================
# НАЛАШТУВАННЯ (ENV)
# =====================
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "kovalenko55555@gmail.com")  # залишено як бек-канал
DRY_RUN = int(os.getenv("DRY_RUN", "1"))  # 1 = тест, не відправляти
OUT_DIR = os.getenv("OUT_DIR", "out")
os.makedirs(OUT_DIR, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "555406850").strip()  # ваш DM

# Логічні назви
COL_PRODUCT_STD = "Інгредієнти"
COL_CAT_STD     = "Категорія"
COL_STORE_A_STD = "Склад Боголюбова"
COL_STORE_B_STD = "Склад Європейська, 31а"
COL_LIMIT_STD   = "Ліміт"

STORE_A_NAME = "Боголюбова"
STORE_B_NAME = "Європейська, 31а"


def _clean_text(s: str) -> str:
    if pd.isna(s):
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\xa0", " ").replace("\n", " ").replace("\r", " ")
    s = " ".join(s.split())
    return s.strip()


def parse_qty_and_unit(val):
    if pd.isna(val):
        return 0.0, None
    s = str(val).strip()
    s = unicodedata.normalize("NFKC", s).replace("\xa0", " ")
    s = re.sub(r'(?<=\d)\s+(?=\d)', '', s)  # "2 000,000" -> "2000,000"
    s = s.replace(",", ".")
    m_num = re.search(r"(-?\d+(?:\.\d+)?)", s)
    qty = float(m_num.group(1)) if m_num else 0.0
    m_unit = re.search(r"(шт|л|кг)", s, flags=re.IGNORECASE)
    unit = m_unit.group(1).lower() if m_unit else None
    return qty, unit


def read_excel_any(path_or_bytes, header=None):
    try:
        if isinstance(path_or_bytes, (str, os.PathLike)):
            return pd.read_excel(path_or_bytes, engine="openpyxl", header=header)
        else:
            return pd.read_excel(io.BytesIO(path_or_bytes), engine="openpyxl", header=header)
    except Exception as e:
        if isinstance(path_or_bytes, (str, os.PathLike)) and str(path_or_bytes).lower().endswith(".xls"):
            try:
                import xlrd  # noqa
                if isinstance(path_or_bytes, (str, os.PathLike)):
                    return pd.read_excel(path_or_bytes, engine="xlrd", header=header)
                else:
                    return pd.read_excel(io.BytesIO(path_or_bytes), engine="xlrd", header=header)
            except Exception as e2:
                raise RuntimeError("Не вдалося прочитати .xls. Збережіть як .xlsx або встановіть xlrd==2.0.1") from e2
        raise


def read_stock_excel(path_or_bytes):
    df_probe = read_excel_any(path_or_bytes, header=None)
    key_tokens = ["нгредієн", "атегор", "боголюб", "європейсь", "лім", "європейська", "31а"]
    header_idx = None
    for i in range(min(10, len(df_probe))):
        row_vals = [_clean_text(v).lower() for v in df_probe.iloc[i].tolist()]
        hit = sum(any(tok in val for val in row_vals) for tok in key_tokens)
        if hit >= 3:
            header_idx = i
            break
    if header_idx is None:
        header_idx = 0

    df = read_excel_any(path_or_bytes, header=header_idx)
    df.columns = [_clean_text(c) for c in df.columns]

    def pick(colnames, needles):
        for c in colnames:
            lc = c.lower()
            if any(n in lc for n in needles):
                return c
        return None

    col_product = pick(df.columns, ["інгредієн", "товар", "назва"])
    col_cat     = pick(df.columns, ["категор"])
    col_a       = pick(df.columns, ["боголюб"])
    col_b       = pick(df.columns, ["європейсь", "європейська", "31а"])
    col_limit   = pick(df.columns, ["ліміт", "лимит"])

    missing = []
    if not col_product: missing.append(COL_PRODUCT_STD)
    if not col_cat:     missing.append(COL_CAT_STD)
    if not col_a:       missing.append(COL_STORE_A_STD)
    if not col_b:       missing.append(COL_STORE_B_STD)
    if not col_limit:   missing.append(COL_LIMIT_STD)
    if missing:
        raise ValueError(f"У файлі бракує очікуваних колонок: {missing}\nЗнайдені: {list(df.columns)}")

    df["_qty_a"], df["_unit_a"]         = zip(*df[col_a].map(parse_qty_and_unit))
    df["_qty_b"], df["_unit_b"]         = zip(*df[col_b].map(parse_qty_and_unit))
    df["_limit_qty"], df["_limit_unit"] = zip(*df[col_limit].map(parse_qty_and_unit))

    df["product_name"] = df[col_product].astype(str).str.strip()
    df["category"]     = df[col_cat].astype(str).str.strip()
    df["_limit_per_store"] = df["_limit_qty"].apply(lambda x: math.ceil((x or 0)/2.0))

    def pick_unit(row):
        return row["_limit_unit"] or row["_unit_a"] or row["_unit_b"] or "шт"
    df["_unit"] = df.apply(pick_unit, axis=1)
    return df


def load_suppliers(df_sup):
    cols = {c.lower().strip(): c for c in df_sup.columns}
    pname = next((cols[k] for k in cols if k in ["product_name","товар","інгредієнти","назва товару","інгредієнт","назва"]), None)
    sname = next((cols[k] for k in cols if k in ["supplier_name","постачальник","постач","vendor","постачальники"]), None)
    psize = next((cols[k] for k in cols if k in ["pack_size","кратність","упаковка","кратнiсть","кратність упаковки"]), None)
    if not pname or not sname:
        raise ValueError("У довіднику немає обов'язкових колонок product_name/товар та supplier_name/постачальник")
    df = df_sup.copy()
    df.rename(columns={pname:"product_name", sname:"supplier_name"}, inplace=True)
    if psize and psize in df.columns:
        df.rename(columns={psize:"pack_size"}, inplace=True)
    else:
        df["pack_size"] = 1
    df["product_name"] = df["product_name"].astype(str).str.strip()
    df["supplier_name"] = df["supplier_name"].astype(str).str.strip()
    df["pack_size"] = pd.to_numeric(df["pack_size"], errors="coerce").fillna(1).astype(int)
    return df[["product_name","supplier_name","pack_size"]]


def compute_orders(df_stock, df_sup):
    merged = df_stock.merge(df_sup, how="left", on="product_name")
    merged["pack_size"] = merged["pack_size"].fillna(1).astype(int)
    merged["supplier_name"] = merged["supplier_name"].fillna("Невідомий постачальник")

    def make_po(store_col_qty, store_name):
        m = merged.copy()
        m["stock_qty"] = m[store_col_qty]
        m["need"] = (m["_limit_per_store"] - m["stock_qty"]).clip(lower=0)

        def round_pack(row):
            if row["need"] <= 0:
                return 0
            return int(math.ceil(row["need"] / row["pack_size"]) * row["pack_size"])
        m["order_qty"] = m.apply(round_pack, axis=1)
        m = m[m["order_qty"] > 0].copy()
        m["unit"] = m["_unit"]
        cols = ["supplier_name","product_name","category","unit","stock_qty","_limit_per_store","pack_size","order_qty"]
        out = m[cols].sort_values(["supplier_name","product_name"]).rename(columns={"_limit_per_store":"limit_per_store"})
        out.insert(0, "store", store_name)
        return out

    po_a = make_po("_qty_a", STORE_A_NAME)
    po_b = make_po("_qty_b", STORE_B_NAME)
    return po_a, po_b


def ai_comment(df_po, store_name):
    if df_po.empty:
        return f"Магазин {store_name}: замовлення не потрібне — усі позиції вище ліміту."
    total = len(df_po)
    top = ", ".join(df_po.sort_values("order_qty", ascending=False)["product_name"].head(3))
    return f"Магазин {store_name}: {total} позицій до замовлення. Найбільша потреба: {top if top else '—'}."


def export_csv_bytes(df, filename_hint):
    return (filename_hint, df.to_csv(index=False).encode("utf-8-sig"))


# -------------- Telegram --------------
def tg_api(method):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задано у .env")
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"

def tg_send_message(text):
    if DRY_RUN:
        print("[DRY_RUN][TG] sendMessage:", text[:1200])
        return
    url = tg_api("sendMessage")
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    r = requests.post(url, data=data, timeout=30)
    r.raise_for_status()

def tg_send_document(path, caption=None):
    if DRY_RUN:
        print(f"[DRY_RUN][TG] sendDocument: {path} (caption={caption})")
        return
    url = tg_api("sendDocument")
    with open(path, "rb") as f:
        files = {"document": (os.path.basename(path), f)}
        data = {"chat_id": TELEGRAM_CHAT_ID}
        if caption:
            data["caption"] = caption[:1024]  # TG caption limit
            data["parse_mode"] = "HTML"
        r = requests.post(url, data=data, files=files, timeout=60)
        r.raise_for_status()


def process_and_send(stock_path, suppliers_path):
    # 1) вхідні дані
    df_stock = read_stock_excel(stock_path)
    if suppliers_path.lower().endswith((".xls",".xlsx")):
        df_sup_raw = read_excel_any(suppliers_path, header=0)
    else:
        df_sup_raw = pd.read_csv(suppliers_path)
    df_sup = load_suppliers(df_sup_raw)

    # 2) розрахунок
    po_a, po_b = compute_orders(df_stock, df_sup)

    # 3) експорт у CSV
    saved = []
    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR, exist_ok=True)

    if not po_a.empty:
        pa = os.path.join(OUT_DIR, "PO_Боголюбова.csv")
        po_a.to_csv(pa, index=False, encoding="utf-8-sig")
        saved.append(pa)
    if not po_b.empty:
        pb = os.path.join(OUT_DIR, "PO_Європейська_31а.csv")
        po_b.to_csv(pb, index=False, encoding="utf-8-sig")
        saved.append(pb)

    # 4) текст для Telegram
    comment_a = ai_comment(po_a, STORE_A_NAME)
    comment_b = ai_comment(po_b, STORE_B_NAME)
    summary = f"{comment_a}\n{comment_b}"
    print("[LOCAL SAVE]", " | ".join(saved) if saved else "—")
    print("[TG BODY]\n", summary)

    # 5) надсилання в Telegram
    try:
        tg_send_message(f"<b>AI Beer Stock Manager</b>\n{summary}")
        for p in saved:
            cap = f"Замовлення: <code>{os.path.basename(p)}</code>"
            tg_send_document(p, caption=cap)
    except Exception as e:
        print("[TG ERROR]", e)
        if DRY_RUN:
            print("DRY_RUN активний або відсутній токен — це очікувано під час тесту.")

    # 6) (необов'язково) Email-лог у DRY_RUN стилі
    att = []
    if not po_a.empty:
        att.append(export_csv_bytes(po_a, "PO_Боголюбова.csv"))
    if not po_b.empty:
        att.append(export_csv_bytes(po_b, "PO_Європейська_31а.csv"))
    print("[DRY_RUN] E-mail не використовується; канал доставки — Telegram.")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="AI Beer Stock Manager -> Telegram")
    p.add_argument("--stock", required=True, help="Шлях до Excel із залишками (.xlsx рекомендовано)")
    p.add_argument("--suppliers", default="suppliers.csv", help="Шлях до suppliers.csv або .xlsx")
    args = p.parse_args()
    process_and_send(args.stock, args.suppliers)
