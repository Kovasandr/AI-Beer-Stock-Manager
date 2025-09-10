import os

DRY_RUN = os.getenv("DRY_RUN", "1") == "1"
DEFAULT_LEAD_DAYS = int(os.getenv("DEFAULT_LEAD_DAYS", "2"))
DEFAULT_SAFETY_DAYS = int(os.getenv("DEFAULT_SAFETY_DAYS", "1"))
TARGET_DAYS_OF_COVER = int(os.getenv("TARGET_DAYS_OF_COVER", "3"))
FROM_EMAIL = os.getenv("FROM_EMAIL", "")
FROM_EMAIL_APP_PASSWORD = os.getenv("FROM_EMAIL_APP_PASSWORD", "")