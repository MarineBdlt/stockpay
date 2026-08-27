"""
WSGI PythonAnywhere — une seule web app, deux chemins :
  /aquaviva  → app aquaviva
  /stockpay  → Stockpay

À utiliser comme fichier WSGI de la web app (à la place du WSGI par défaut).
Adapte AQUAVIVA_MODULE si besoin (voir commentaires).
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── Chemins (username détecté via home) ──────────────────────────
HOME = Path.home()
STOCKPAY_DIR = HOME / "stockpay"
AQUAVIVA_DIR = HOME / "aquaviva"

for p in (str(STOCKPAY_DIR), str(AQUAVIVA_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv

load_dotenv(STOCKPAY_DIR / ".env")

from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.middleware.proxy_fix import ProxyFix

# ── Stockpay ─────────────────────────────────────────────────────
from app import app as stockpay_app  # noqa: E402

stockpay_app.config["APPLICATION_ROOT"] = "/stockpay"

# ── Aquaviva ─────────────────────────────────────────────────────
# Essaie les points d’entrée courants. Si ça échoue, définis AQUAVIVA_IMPORT
# dans le .env Stockpay, ex. : AQUAVIVA_IMPORT=flask_app:app
import importlib
import os


def _load_aquaviva():
    custom = os.environ.get("AQUAVIVA_IMPORT", "").strip()
    candidates = []
    if custom and ":" in custom:
        mod_name, attr = custom.split(":", 1)
        candidates.append((mod_name, attr))
    candidates.extend(
        [
            ("flask_app", "app"),
            ("app", "app"),
            ("wsgi", "application"),
            ("application", "app"),
        ]
    )
    errors = []
    for mod_name, attr in candidates:
        try:
            mod = importlib.import_module(mod_name)
            obj = getattr(mod, attr)
            return obj
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{mod_name}:{attr} → {exc}")
    raise ImportError(
        "Impossible de charger aquaviva. "
        "Ajoute dans ~/stockpay/.env par ex. AQUAVIVA_IMPORT=flask_app:app\n"
        + "\n".join(errors)
    )


aquaviva_app = _load_aquaviva()
try:
    # Flask
    aquaviva_app.config["APPLICATION_ROOT"] = "/aquaviva"
except Exception:
    pass


def root_app(environ, start_response):
    """Redirige / vers /stockpay/ (change vers /aquaviva/ si tu préfères)."""
    start_response(
        "302 Found",
        [("Location", "/stockpay/"), ("Content-Type", "text/plain")],
    )
    return [b"Redirecting to /stockpay/"]


application = DispatcherMiddleware(
    root_app,
    {
        "/stockpay": stockpay_app,
        "/aquaviva": aquaviva_app,
    },
)

application = ProxyFix(application, x_for=1, x_proto=1, x_host=1, x_prefix=1)
