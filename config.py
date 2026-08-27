"""Configuration StockPay — scan disque, coûts PythonAnywhere, e-mails."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
    DATABASE = os.environ.get("STOCKPAY_DB", str(BASE_DIR / "stockpay.db"))

    # Marque : Stockpay · Fait par WeBBap
    APP_NAME = os.environ.get("APP_NAME", "Stockpay")
    APP_CREDIT = os.environ.get("APP_CREDIT", "Fait par webbap")
    APP_TAGLINE = os.environ.get(
        "APP_TAGLINE", "hébergement & paiement sécurisé"
    )

    # Dossier parent qui contient aquaviva/, cle_corse/, stockpay/, …
    SCAN_ROOT = Path(os.environ.get("STOCKPAY_SCAN_ROOT", str(BASE_DIR.parent)))

    EXCLUDE_DIRS = {
        "stockpay",
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        ".cache",
        "tmp",
        "node_modules",
    }

    CURRENCY = "EUR"

    # Coûts mensuels PythonAnywhere à répartir (valeurs par défaut ~ plan ~10 €)
    # Disque = quota stockage · Webapp = app / workers · RAM = CPU / mémoire / tasks
    COST_DISK = float(os.environ.get("STOCKPAY_COST_DISK", "4.00"))
    COST_WEBAPP = float(os.environ.get("STOCKPAY_COST_WEBAPP", "3.50"))
    COST_RAM = float(os.environ.get("STOCKPAY_COST_RAM", "2.50"))
    # % du coût alloué à facturer aux projets (100 = tout · 80 = tu absorbs 20 %)
    BILLING_PERCENT = float(os.environ.get("STOCKPAY_BILLING_PERCENT", "100"))

    ADMIN_PASSWORD = os.environ.get("STOCKPAY_ADMIN_PASSWORD", "admin")

    PAYMENT_DUE_DAY = int(os.environ.get("STOCKPAY_PAYMENT_DUE_DAY", "5"))
    REMINDER_COOLDOWN_DAYS = int(os.environ.get("STOCKPAY_REMINDER_COOLDOWN", "7"))

    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get(
        "MAIL_DEFAULT_SENDER", os.environ.get("MAIL_USERNAME", "stockpay@localhost")
    )
    MAIL_SUBJECT_PREFIX = os.environ.get("MAIL_SUBJECT_PREFIX", "[Stockpay] ")

    # URL publique HTTPS du site (PythonAnywhere) — utilisée pour Stripe return/cancel
    # Ex. https://tonuser.pythonanywhere.com  ou  https://pay.webbap.fr
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

    # Stripe Checkout (sk_test_… / sk_live_…). Vide = paiement manuel uniquement.
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    # Confirmation manuelle désactivée : seul un paiement Stripe vérifié marque « payé »
    STRIPE_ALLOW_MANUAL = os.environ.get("STRIPE_ALLOW_MANUAL", "false").lower() == "true"

    # Mentions facture (émetteur)
    INVOICE_ISSUER_NAME = os.environ.get("INVOICE_ISSUER_NAME", "Stockpay")
    INVOICE_ISSUER_DETAILS = os.environ.get(
        "INVOICE_ISSUER_DETAILS",
        "Fait par webbap · hébergement mutualisé · contribution mensuelle",
    )
    INVOICE_FOOTER = os.environ.get(
        "INVOICE_FOOTER",
        "Document généré par Stockpay — Fait par webbap. TVA non applicable — "
        "exonération ou hors champ (à adapter selon votre situation).",
    )


def bytes_to_billed_gb(size_bytes: int) -> int:
    """Arrondit à l’entier de Go supérieur (min. 1 Go si le dossier n’est pas vide)."""
    import math

    if size_bytes <= 0:
        return 0
    gb = size_bytes / (1024**3)
    return max(1, math.ceil(gb))
