"""Envoi d’e-mails (impayés + rappels)."""

from __future__ import annotations

import smtplib
from datetime import date, datetime, timezone
from email.message import EmailMessage
from typing import Any

from config import Config
from models import log_email, record_reminder, unpaid_projects


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _smtp_configured() -> bool:
    return bool(Config.MAIL_SERVER and Config.MAIL_DEFAULT_SENDER)


def send_raw(to: str, subject: str, body: str) -> tuple[bool, str]:
    """Envoie un mail. Sans SMTP : écrit en console (mode dev)."""
    full_subject = f"{Config.MAIL_SUBJECT_PREFIX}{subject}"
    if not _smtp_configured():
        print(f"─── {Config.APP_NAME} mail (simulation) ───")
        print(f"À : {to}")
        print(f"Sujet : {full_subject}")
        print(body)
        print("─────────────────────────────────")
        return True, "simulated"

    msg = EmailMessage()
    msg["From"] = Config.MAIL_DEFAULT_SENDER
    msg["To"] = to
    msg["Subject"] = full_subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(Config.MAIL_SERVER, Config.MAIL_PORT, timeout=30) as smtp:
            if Config.MAIL_USE_TLS:
                smtp.starttls()
            if Config.MAIL_USERNAME:
                smtp.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            smtp.send_message(msg)
        return True, "sent"
    except Exception as exc:  # noqa: BLE001 — on journalise l’échec
        return False, str(exc)


def build_unpaid_body(project: dict[str, Any], reminder: bool = False) -> str:
    kind = "rappel" if reminder else "avis"
    return (
        f"Bonjour,\n\n"
        f"Ceci est un {kind} concernant le projet « {project['display_name']} » "
        f"(dossier `{project['folder_name']}`).\n\n"
        f"Espace utilisé : {project['size_human']} "
        f"(facturé {project['billed_gb']} Go)\n"
        f"Part disque : {float(project.get('price_disk') or 0):.2f} €\n"
        f"Part webapp + RAM : {float(project.get('price_shared') or 0):.2f} €\n"
        f"Tarif du mois : {project['monthly_price']:.2f} €\n\n"
        f"Le paiement n’a pas encore été enregistré pour ce mois-ci.\n"
        f"Merci de régulariser dès que possible via {Config.APP_NAME}.\n\n"
        f"— {Config.APP_NAME} · {Config.APP_CREDIT}\n"
    )


def send_payment_notice(project: dict[str, Any], reminder: bool = False) -> tuple[bool, str]:
    email = (project.get("email") or "").strip()
    if not email:
        return False, "pas d’e-mail"
    subject = (
        f"Rappel de paiement — {project['display_name']}"
        if reminder
        else f"Paiement en attente — {project['display_name']}"
    )
    body = build_unpaid_body(project, reminder=reminder)
    ok, detail = send_raw(email, subject, body)
    kind = "reminder" if reminder else "unpaid"
    log_email(project["id"], kind, email, subject, ok=ok, detail=detail)
    if ok:
        record_reminder(project["id"])
    return ok, detail


def should_send_reminder(project: dict[str, Any], force: bool = False) -> bool:
    if force:
        return True
    if not project.get("needs_payment"):
        return False
    # Attendre le jour d’échéance du mois avant les envois automatiques
    if date.today().day < Config.PAYMENT_DUE_DAY:
        return False
    last = _parse_iso(project.get("last_reminder_at"))
    if last is None:
        return True
    now = datetime.now(timezone.utc)
    delta = now - last
    return delta.days >= Config.REMINDER_COOLDOWN_DAYS


def send_due_reminders(force: bool = False) -> list[dict[str, Any]]:
    """Envoie les avis / rappels pour tous les projets impayés éligibles."""
    results = []
    for project in unpaid_projects():
        if not should_send_reminder(project, force=force):
            results.append(
                {
                    "project": project["folder_name"],
                    "skipped": True,
                    "reason": "cooldown",
                }
            )
            continue
        is_reminder = bool(project.get("last_reminder_at"))
        ok, detail = send_payment_notice(project, reminder=is_reminder)
        results.append(
            {
                "project": project["folder_name"],
                "skipped": False,
                "ok": ok,
                "detail": detail,
                "reminder": is_reminder,
            }
        )
    return results
