"""État du circuit paiement / déploiement (prêt avant clés Stripe)."""

from __future__ import annotations

from typing import Any

from config import Config
from payments import stripe_enabled


def circuit_status() -> dict[str, Any]:
    """Checklist visible dans l’admin : ce qui est prêt vs à brancher après mise en ligne."""
    secret = Config.SECRET_KEY or ""
    stripe_key = Config.STRIPE_SECRET_KEY or ""
    checks = [
        {
            "id": "secret",
            "label": "SECRET_KEY personnalisée",
            "ok": bool(secret) and secret != "dev-change-me-in-production",
            "hint": "Obligatoire en prod (sessions / admin).",
        },
        {
            "id": "admin",
            "label": "Mot de passe admin changé",
            "ok": Config.ADMIN_PASSWORD not in ("admin", "changez-moi", ""),
            "hint": "STOCKPAY_ADMIN_PASSWORD dans le .env",
        },
        {
            "id": "scan",
            "label": "Racine de scan définie",
            "ok": bool(Config.SCAN_ROOT),
            "hint": f"STOCKPAY_SCAN_ROOT = {Config.SCAN_ROOT}",
        },
        {
            "id": "public_url",
            "label": "URL publique HTTPS",
            "ok": bool(Config.PUBLIC_BASE_URL) and Config.PUBLIC_BASE_URL.startswith("https://"),
            "hint": "PUBLIC_BASE_URL=https://ton-user.pythonanywhere.com (pour Stripe)",
        },
        {
            "id": "stripe_key",
            "label": "Clé Stripe live",
            "ok": stripe_enabled() and stripe_key.startswith("sk_live_"),
            "hint": "STRIPE_SECRET_KEY=sk_live_… (après mise en ligne)",
            "optional_until_online": True,
        },
        {
            "id": "stripe_test",
            "label": "Clé Stripe test (dev)",
            "ok": stripe_enabled() and stripe_key.startswith("sk_test_"),
            "hint": "sk_test_… uniquement pour essais — pas pour de vrais paiements",
            "optional_until_online": True,
            "info_only": True,
        },
        {
            "id": "webhook",
            "label": "Webhook Stripe",
            "ok": bool(Config.STRIPE_WEBHOOK_SECRET) and Config.STRIPE_WEBHOOK_SECRET.startswith("whsec_"),
            "hint": "Endpoint /webhook/stripe · événement checkout.session.completed",
            "optional_until_online": True,
        },
        {
            "id": "mail",
            "label": "SMTP e-mails",
            "ok": bool(Config.MAIL_SERVER and Config.MAIL_DEFAULT_SENDER),
            "hint": "Sinon les rappels s’affichent seulement dans les logs",
            "optional_until_online": True,
        },
    ]

    stripe_ready = stripe_enabled() and (
        stripe_key.startswith("sk_live_") or stripe_key.startswith("sk_test_")
    )
    go_live_ready = all(
        c["ok"]
        for c in checks
        if c["id"] in ("secret", "admin", "public_url", "stripe_key", "webhook")
    )

    return {
        "checks": checks,
        "stripe_enabled": stripe_enabled(),
        "stripe_mode": (
            "live"
            if stripe_key.startswith("sk_live_")
            else "test"
            if stripe_key.startswith("sk_test_")
            else "off"
        ),
        "stripe_ready": stripe_ready,
        "go_live_ready": go_live_ready,
        "webhook_url_hint": (
            f"{Config.PUBLIC_BASE_URL.rstrip('/')}/webhook/stripe"
            if Config.PUBLIC_BASE_URL
            else "https://TON-DOMAINE/webhook/stripe"
        ),
        "manual_ok": False,
    }
