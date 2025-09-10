import os
import openai
import pandas as pd

openai.api_key = os.getenv("OPENAI_API_KEY")

def forecast_with_ai(sales_df: pd.DataFrame, sku: str, days: int = 7):
    """
    Використовує OpenAI для прогнозу продажів на наступні дні
    """
    sales_text = sales_df[sales_df["sku"] == sku][["date", "qty"]].to_csv(index=False)
    prompt = f"""
    Ось історія продажів товару {sku}:
    {sales_text}
    
    Прогнозуй продажі на наступні {days} днів.
    Відповідай у форматі: дата,кількість
    """
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message["content"]

def generate_supplier_message(po_df: pd.DataFrame):
    """
    Формує зрозумілий текст замовлення для постачальника
    """
    items = "\n".join([f"{row.sku} ({row.name}) — {row.need_qty} шт." for row in po_df.itertuples()])
    prompt = f"""
    Напиши ввічливий лист постачальнику українською.
    У листі повинно бути:
    - Привітання
    - Пояснення, що це автоматизоване замовлення на основі прогнозу продажів
    - Список товарів:
    {items}
    - Подяка
    """
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message["content"]
