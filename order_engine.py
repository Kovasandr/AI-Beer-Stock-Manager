# -*- coding: utf-8 -*-
"""
AI Beer Stock Manager — дві точки (Боголюбова / Європейська, 31а)
Експорт у .xlsx з «людськими» колонками + список товарів без постачальника.

Функції:
- Читає Excel із залишками (терпить шапку; знаходить рядок заголовків)
- Парсить кількості та одиниці (шт/л/кг)
- Ділить Ліміт навпіл для кожного магазину (ceil)
- Рахує потребу окремо по магазинах, округляє до pack_size з suppliers
- Формує 2 XLSX зі зрозумілими колонками (аналог стилю файлу з пошти)
- Формує третій XLSX: MISSING_SUPPLIERS.xlsx — продукти без постачальника
- Надсилає все в Telegram (якщо DRY_RUN=0)

ENV:
- DRY_RUN=1|0
- OUT_DIR=out
- TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import os, io, re, math, unicodedata, pandas as pd, requests

# --------- env loader ---------
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "kovalenko55555@gmail.com")  # необов'язково
DRY_RUN = int(os.getenv("DRY_RUN", "1"))
OUT_DIR = os.getenv("OUT_DIR", "out")
os.makedirs(OUT_DIR, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "555406850").strip()

# Базові назви колонок
COL_PRODUCT_STD = "Інгредієнти"
COL_CAT_STD     = "Категорія"
COL_STORE_A_STD = "Склад Боголюбова"
COL_STORE_B_STD = "Склад Європейська, 31а"
COL_LIMIT_STD   = "Ліміт"

STORE_A_NAME = "Боголюбова"
STORE_B_NAME = "Європейська, 31а"


def _clean_text(s: str) -> str:
    if pd.isna(s): return ""
    s = str(s)
    s = unicodedata.normalize("NFKC", s).replace("\xa0", " ").replace("\n", " ").replace("\r", " ")
    return " ".join(s.split()).strip()


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
    except Exception:
        # друга спроба для .xls (якщо встановлено xlrd)
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
    # 1) Проба без заголовків — шукаємо рядок із заголовками
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

    # 2) Читаємо з тим заголовком
    df = read_excel_any(path_or_bytes, header=header_idx)
    df.columns = [_clean_text(c) for c in df.columns]

    # 3) Знаходимо потрібні колонки (терпимо варіанти)
    def pick(colnames, needles):
        for c in colnames:
            if any(n in c.lower() for n in needles):
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
        raise ValueError(f"У файлі відсутні очікувані колонки: {missing}. Є колонки: {list(df.columns)}")

    # 4) Парсимо кількості/одиниці
    df["_qty_a"], df["_unit_a"]         = zip(*df[col_a].map(parse_qty_and_unit))
    df["_qty_b"], df["_unit_b"]         = zip(*df[col_b].map(parse_qty_and_unit))
    df["_limit_qty"], df["_limit_unit"] = zip(*df[col_limit].map(parse_qty_and_unit))

    df["product_name"] = df[col_product].astype(str).str.strip()
    df["category"]     = df[col_cat].astype(str).str.strip()

    # Ліміт навпіл (ceil)
    df["_limit_per_store"] = df["_limit_qty"].apply(lambda x: math.ceil((x or 0) / 2.0))

    # Загальна одиниця: пріоритет — ліміт, далі склади, інакше "шт"
    def pick_unit(row):
        return row["_limit_unit"] or row["_unit_a"] or row["_unit_b"] or "шт"
    df["_unit"] = df.apply(pick_unit, axis=1)
    return df


def load_suppliers(df_sup):
    cols = {c.lower().strip(): c for c in df_sup.columns}
    pname = next((cols[k] for k in cols if k in ["product_name", "товар", "інгредієнти", "назва товару", "інгредієнт", "назва"]), None)
    sname = next((cols[k] for k in cols if k in ["supplier_name", "постачальник", "постач", "vendor", "постачальники"]), None)
    psize = next((cols[k] for k in cols if k in ["pack_size", "кратність", "упаковка", "кратнiсть", "кратність упаковки"]), None)
    if not pname or not sname:
        raise ValueError("У довіднику немає обов'язкових колонок product_name/товар та supplier_name/постачальник")
    df = df_sup.copy()
    df.rename(columns={pname: "product_name", sname: "supplier_name"}, inplace=True)
    if psize and psize in df.columns:
        df.rename(columns={psize: "pack_size"}, inplace=True)
    else:
        df["pack_size"] = 1
    df["product_name"] = df["product_name"].astype(str).str.strip()
    df["supplier_name"] = df["supplier_name"].astype(str).str.strip()
    df["pack_size"] = pd.to_numeric(df["pack_size"], errors="coerce").fillna(1).astype(int)
    return df[["product_name", "supplier_name", "pack_size"]]


def compute_orders_and_missing(df_stock, df_sup):
    merged = df_stock.merge(df_sup, how="left", on="product_name")
    merged["pack_size"] = merged["pack_size"].fillna(1).astype(int)
    merged["supplier_name"] = merged["supplier_name"].fillna("Невідомий постачальник")

    # Список відсутніх постачальників
    missing = merged[merged["supplier_name"].eq("Невідомий постачальник")][
        ["product_name", "category", "_unit"]
    ].drop_duplicates().rename(columns={
        "product_name": "Інгредієнти",
        "category": "Категорія",
        "_unit": "Одиниця"
    })

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

        # Формат під «людську» таблицю (аналог експорту)
        out = m[["product_name", "category", "unit", "_limit_per_store", "stock_qty", "order_qty", "pack_size", "supplier_name"]].rename(columns={
            "product_name": "Інгредієнти",
            "category": "Категорія",
            "unit": "Одиниця",
            "_limit_per_store": "Ліміт на магазин",
            "stock_qty": "Залишок",
            "order_qty": "Замовити",
            "pack_size": "Кратність",
            "supplier_name": "Постачальник"
        }).sort_values(["Постачальник", "Інгредієнти"])
        return out

    po_a = make_po("_qty_a", STORE_A_NAME)
    po_b = make_po("_qty_b", STORE_B_NAME)
    return po_a, po_b, missing


# --------- Telegram helpers ---------
def tg_api(method):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задано")
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"

def tg_send_message(text):
    if DRY_RUN:
        print("[DRY_RUN][TG] sendMessage:", text[:1200])
        return
    r = requests.post(tg_api("sendMessage"), data={
        "chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True
    }, timeout=30)
    r.raise_for_status()

def tg_send_document(path, caption=None):
    if DRY_RUN:
        print(f"[DRY_RUN][TG] sendDocument: {path} (caption={caption})")
        return
    with open(path, "rb") as f:
        files = {"document": (os.path.basename(path), f)}
        data = {"chat_id": TELEGRAM_CHAT_ID}
        if caption:
            data["caption"] = caption[:1024]; data["parse_mode"] = "HTML"
        r = requests.post(tg_api("sendDocument"), data=data, files=files, timeout=60)
        r.raise_for_status()


def save_xlsx(df: pd.DataFrame, path: str):
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Замовлення")
        ws = writer.book.active
        # автоширина
        for col_idx, col in enumerate(df.columns, start=1):
            max_len = max([len(str(col))] + [len(str(v)) for v in df[col].astype(str).tolist()])
            ws.column_dimensions[ws.cell(1, col_idx).column_letter].width = min(max_len + 2, 60)


def ai_line(df_po: pd.DataFrame, store_name: str) -> str:
    if df_po.empty:
        return f"Магазин {store_name}: замовлення не потрібне — усі позиції вище ліміту."
    sums = df_po.groupby("Одиниця")["Замовити"].sum()
    def fmt(x): return str(int(x)) if float(x).is_integer() else f"{x:.2f}"
    prefer = ["л", "кг", "шт"]
    parts = [f"{fmt(sums[u])} {u}" for u in prefer if u in sums and sums[u] > 0]
    parts += [f"{fmt(v)} {u}" for u, v in sums.items() if u not in prefer and v > 0]
    top = ", ".join(df_po.sort_values("Замовити", ascending=False)["Інгредієнти"].head(3))
    return f"Магазин {store_name}: {len(df_po)} позицій. Підсумок: {', '.join(parts) if parts else '0'}. Топ: {top if top else '—'}."


def process_and_send(stock_path, suppliers_path):
    # 1) Вхідні дані
    df_stock = read_stock_excel(stock_path)
    if suppliers_path.lower().endswith((".xls", ".xlsx")):
        df_sup_raw = read_excel_any(suppliers_path, header=0)
    else:
        df_sup_raw = pd.read_csv(suppliers_path)
    df_sup = load_suppliers(df_sup_raw)

    # 2) Розрахунок
    po_a, po_b, missing = compute_orders_and_missing(df_stock, df_sup)

    # 3) Збереження XLSX
    saved_files = []
    if not po_a.empty:
        path_a = os.path.join(OUT_DIR, "PO_Боголюбова.xlsx")
        save_xlsx(po_a, path_a)
        saved_files.append(path_a)
    if not po_b.empty:
        path_b = os.path.join(OUT_DIR, "PO_Європейська_31а.xlsx")
        save_xlsx(po_b, path_b)
        saved_files.append(path_b)
    # Missing suppliers
    if not missing.empty:
        path_m = os.path.join(OUT_DIR, "MISSING_SUPPLIERS.xlsx")
        save_xlsx(missing, path_m)
        saved_files.append(path_m)

    print("[LOCAL SAVE]", " | ".join(saved_files) if saved_files else "—")

    # 4) Повідомлення
    comment_a = ai_line(po_a, STORE_A_NAME)
    comment_b = ai_line(po_b, STORE_B_NAME)
    body = f"{comment_a}\n{comment_b}"
    print("[SUMMARY]\n", body)

    # 5) Відправка в Telegram (xlsx)
    try:
        tg_send_message(f"<b>AI Beer Stock Manager</b>\n{body}")
        for p in saved_files:
            cap = f"<code>{os.path.basename(p)}</code>"
            tg_send_document(p, caption=cap)
    except Exception as e:
        print("[TG ERROR]", e)
        if DRY_RUN:
            print("DRY_RUN активний або відсутній токен — це очікувано під час тесту.")

    return po_a, po_b, missing


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="AI Beer Stock Manager → XLSX + Telegram")
    p.add_argument("--stock", required=True, help="Шлях до Excel із залишками (.xlsx/.xls)")
    p.add_argument("--suppliers", default="suppliers.csv", help="Шлях до suppliers.csv або .xlsx")
    args = p.parse_args()
    process_and_send(args.stock, args.suppliers)
