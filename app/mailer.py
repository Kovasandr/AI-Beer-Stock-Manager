# app/mailer.py
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
import pandas as pd

def build_html(po_df: pd.DataFrame, title: str = "Purchase Order") -> str:
    if po_df is None or po_df.empty:
        return "<p>Замовлень немає — запас достатній.</p>"
    rows = []
    for _, r in po_df.iterrows():
        rows.append(f"<tr><td>{r['sku']}</td><td>{r['name']}</td><td>{int(r['need_qty'])}</td></tr>")
    table = (
        f"<h3>{title}</h3>"
        "<table border='1' cellpadding='6' cellspacing='0'>"
        "<tr><th>SKU</th><th>Назва</th><th>К-сть</th></tr>"
        + "".join(rows) +
        "</table>"
    )
    return table

def send_mail(po_df: pd.DataFrame, subject: str, to_email: str, dry_run: bool = True):
    host = os.getenv("SMTP_HOST", "")
    port = int((os.getenv("SMTP_PORT") or "587").strip())
    user = os.getenv("FROM_EMAIL", "")
    password = os.getenv("FROM_EMAIL_APP_PASSWORD", "")

    html = build_html(po_df, title=subject)

    if dry_run or not all([host, port, user, password, to_email]):
        # Прев’ю без відправки
        return {"sent": False, "preview_html": html, "reason": "DRY_RUN або не налаштовано SMTP"}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    # Додаємо як вкладення CSV з PO
    if po_df is not None and not po_df.empty:
        csv_bytes = po_df.to_csv(index=False).encode("utf-8")
        part = MIMEBase("application", "octet-stream")
        part.set_payload(csv_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment; filename=PO.csv")
        msg.attach(part)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [to_email], msg.as_string())

    return {"sent": True, "preview_html": html}
