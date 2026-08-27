"""
state.py
--------
Einfache Zustandsverwaltung, um zu verhindern, dass durch mehrere
Cron-Versuche innerhalb eines Zeitfensters (siehe Workflow-Datei)
mehrfach dieselbe Report-Mail an einem Tag verschickt wird.

Der Zustand (Datum + zuletzt erfolgreich verschickter Run-Typ) wird in
einer kleinen JSON-Datei im Repository gespeichert und nach jedem
erfolgreichen Versand vom Workflow zurück ins Repo committet.
"""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def already_sent_today(state_path: str, run_type: str) -> bool:
    """Prüft, ob für den heutigen Tag (UTC) bereits erfolgreich für diesen
    run_type (morning/evening) eine E-Mail verschickt wurde."""
    if not os.path.exists(state_path):
        return False
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Konnte Zustandsdatei nicht lesen (%s) – gehe von 'noch nicht gesendet' aus", exc)
        return False

    sent_today = data.get(_today_str(), [])
    return run_type in sent_today


def mark_sent(state_path: str, run_type: str) -> None:
    """Markiert den heutigen run_type als erfolgreich versendet.
    Alte Einträge (andere Tage) werden aufgeräumt, damit die Datei klein bleibt."""
    today = _today_str()
    data = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001
            data = {}

    # Nur den heutigen Tag behalten (Historie wird nicht gebraucht)
    data = {today: data.get(today, [])}
    if run_type not in data[today]:
        data[today].append(run_type)

    os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
