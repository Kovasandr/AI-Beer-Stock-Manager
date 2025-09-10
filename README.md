# AI Beer Stock Manager

Легка система для автоматичного контролю запасів і формування замовлень.

## Що вміє
- Аналізує продажі та залишки
- Прогнозує потребу з урахуванням тренду (спрощено)
- Формує замовлення постачальнику
- Надсилає email (у режимі `DRY_RUN=1` лише друкує лист у консоль)

## Швидкий старт (локально)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# (опційно) створіть .env на основі .env.example
cp .env.example .env

# Запустити CLI-прорахунок:
python cli.py --sales sample_data/sales.csv --inventory sample_data/inventory.csv --supplier-email test@example.com

# Запустити Streamlit-UI:
streamlit run streamlit_app.py
```

## Запуск у GitHub Actions (крон-джоб)
1. Форкніть репозиторій
2. Додайте **Repository Secrets** (Settings → Secrets and variables → Actions):
   - `SUPPLIER_EMAIL`
   - `FROM_EMAIL`
   - `FROM_EMAIL_APP_PASSWORD` (для Gmail згенерований App Password)
   - `DRY_RUN` = `0` (щоб відправляло email) або `1` (для тесту)
3. Увімкніть workflow `.github/workflows/daily-run.yml` (він запускається щодня о 7:00 UTC)

## Налаштування
- Значення за замовчуванням зберігаються у `.env` (див. `.env.example`)
- Можна підключити Google Sheets замість CSV (плейсхолдер у `app/sheets.py`)

## Демодані
- `sample_data/sales.csv` — історія продажів по днях
- `sample_data/inventory.csv` — поточні залишки та налаштування SKU

## Ліцензія
MIT