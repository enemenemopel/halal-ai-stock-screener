"""
email.py
--------
Versand der Report-E-Mail via SMTP. Zugangsdaten werden AUSSCHLIESSLICH
aus Umgebungsvariablen gelesen (in GitHub Actions: GitHub Secrets).
Niemals Zugangsdaten im Code oder in Dateien speichern.

Erwartet folgende Umgebungsvariablen:
  SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, MAIL_TO
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


class EmailConfigError(Exception):
    pass


class EmailSendError(Exception):
    pass


def _load_smtp_config() -> dict:
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "MAIL_TO"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise EmailConfigError(
            f"Fehlende SMTP-Konfiguration (GitHub Secrets prüfen): {', '.join(missing)}"
        )
    return {
        "host": os.environ["SMTP_HOST"],
        "port": int(os.environ["SMTP_PORT"]),
        "username": os.environ["SMTP_USERNAME"],
        "password": os.environ["SMTP_PASSWORD"],
        "to": os.environ["MAIL_TO"],
    }


def send_report_email(subject: str, html_body: str, text_body: str) -> None:
    """Sendet den Report per E-Mail. Wirft aussagekräftige Exceptions bei Fehlern,
    damit main.py den Fehler klar loggen (und ggf. in GitHub Actions sichtbar
    machen) kann, statt still zu scheitern."""
    try:
        cfg = _load_smtp_config()
    except EmailConfigError as exc:
        logger.error(str(exc))
        raise

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["username"]
    msg["To"] = cfg["to"]
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg["username"], cfg["password"])
            server.sendmail(cfg["username"], [cfg["to"]], msg.as_string())
        logger.info("E-Mail erfolgreich an %s gesendet.", cfg["to"])
    except smtplib.SMTPAuthenticationError as exc:
        raise EmailSendError(
            "SMTP-Authentifizierung fehlgeschlagen. Prüfe SMTP_USERNAME/SMTP_PASSWORD "
            "(bei GMX/Gmail ggf. App-Passwort statt normalem Passwort nötig)."
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailSendError(f"E-Mail-Versand fehlgeschlagen: {exc}") from exc
