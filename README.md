AI Beer Stock Manager

Простий AI-агент для управління запасами: аналізує продажі, рахує замовлення та може автоматично надсилати їх постачальникам.

🔑 Можливості

📊 Читає CSV з історією продажів та залишками на складі

🔮 Прогнозує потребу на основі середньодобових продажів + safety stock

📦 Формує Purchase Order (PO) з урахуванням мін/макс та упаковок

📧 Надсилає email постачальнику (режим DRY_RUN=1 → тільки прев’ю)

🌐 Веб-інтерфейс на Streamlit для швидкої перевірки

🚀 Швидкий старт локально
# 1. Створіть віртуальне середовище
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate # Linux/Mac

# 2. Встановіть залежності
pip install -r requirements.txt

# 3. (опційно) створіть .env на основі .env.example
cp .env.example .env

# 4. Запустіть Streamlit-інтерфейс
streamlit run streamlit_app.py

# або CLI-варіант
python cli.py --sales sample_data/sales.csv --inventory sample_data/inventory.csv

⚙️ Налаштування середовища

Файл .env (приклад у .env.example):

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SUPPLIER_EMAIL=supplier@example.com
DRY_RUN=1   # 1 = тільки прев’ю, 0 = реальна відправка

🤖 GitHub Actions (автоматизація)

Workflow запускається щодня о 07:00 UTC і формує замовлення.

Форкніть репозиторій

Додайте Repository Secrets (Settings → Secrets and variables → Actions):

SUPPLIER_EMAIL → email постачальника, на який відправляється замовлення

FROM_EMAIL → ваша пошта (наприклад, Gmail), з якої надсилаються листи

FROM_EMAIL_APP_PASSWORD → App Password (згенерований у Gmail або іншому поштовому сервісі)

DRY_RUN → 1 (тільки прев’ю) або 0 (реальна відправка)

Активуйте workflow: .github/workflows/daily-run.yml
🧪 Демодані

sample_data/sales.csv — історія продажів (колонки: date, sku, qty)

sample_data/inventory.csv — залишки (колонки: sku, name, stock)

Для швидкої перевірки достатньо завантажити ці файли у Streamlit-UI.

📜 Ліцензія

MIT