# GitHub Automation for AI Beer Stock Manager

## Files
- `github_runner.py` — тягне останній Excel з Gmail (за фільтром), читає `suppliers.csv` і запускає логіку `order_engine`.
- `.github/workflows/generate-po.yml` — GitHub Actions: розклад + ручний запуск, завантаження CSV як артефакт, відправка у Telegram.

## Налаштування
1. Додайте в репозиторії **Secrets**:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `GMAIL_USER`
   - `GMAIL_APP_PASSWORD` (App Password для IMAP)
2. Покладіть `order_engine.py` і `suppliers.csv` у корінь репо.
3. (Опційно) В `requirements.txt` додайте: `pandas openpyxl xlrd==2.0.1 requests python-dotenv`.
4. Запустіть вручну (*Actions → Generate PO and Send to Telegram → Run workflow*) або чекайте CRON.

## Примітка про вашу помилку
Помилка `ModuleNotFoundError: No module named 'app.emailer'` виникла через імпорт з неіснуючого пакета `app`.
Цей пакунок не потрібен — ми використовуємо `order_engine.py` і `github_runner.py`. Видаліть/не використовуйте старий `cli.py`,
або виправте імпорт на відносний і запуск модулем (`python -m`). У цьому пакеті це не потрібно.
