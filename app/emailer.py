import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import tempfile
import pandas as pd
from .config import DRY_RUN, FROM_EMAIL, FROM_EMAIL_APP_PASSWORD

def send_email(subject: str, body: str, to_email: str, po_df: pd.DataFrame):
    if not to_email:
        print("[WARN] to_email не задано. Лист не буде відправлено.")
        return

    # Підготовка вкладення CSV
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tf:
        po_df.to_csv(tf.name, index=False)
        attachment_path = tf.name

    if DRY_RUN:
        print("=== DRY RUN: Email ===")
        print("Subject:", subject)
        print("To:", to_email)
        print("Body:\n", body)
        print("Attachment (csv):", attachment_path)
        return

    if not FROM_EMAIL or not FROM_EMAIL_APP_PASSWORD:
        print("[ERROR] FROM_EMAIL або FROM_EMAIL_APP_PASSWORD відсутні. Встановіть у .env")
        return

    msg = MIMEMultipart()
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    part = MIMEBase("application", "octet-stream")
    with open(attachment_path, "rb") as f:
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename=PO.csv")
    msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(FROM_EMAIL, FROM_EMAIL_APP_PASSWORD)
        server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        print("[OK] Лист відправлено:", to_email)