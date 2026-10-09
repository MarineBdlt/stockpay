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

# ── Aquaviva ─────────────────────────────────────────────────────
# Essaie les points d’entrée courants. Si ça échoue, définis AQUAVIVA_IMPORT
# dans le .env Stockpay, ex. : AQUAVIVA_IMPORT=flask_app:app
import importlib
import os


def _load_aquaviva():
    """Charge Aquaviva sans reprendre le module `app` déjà importé (Stockpay)."""
    custom = os.environ.get("AQUAVIVA_IMPORT", "").strip()
    candidates = []
    if custom and ":" in custom:
        mod_name, attr = custom.split(":", 1)
        candidates.append((mod_name, attr))
    # Pas de ("app", "app") : Stockpay a déjà sys.modules["app"].
    candidates.extend(
        [
            ("booking_engine", "app"),
            ("flask_app", "app"),
            ("wsgi", "application"),
            ("application", "app"),
        ]
    )
    errors = []
    for mod_name, attr in candidates:
        try:
            # Réimport propre depuis ~/aquaviva (évite le cache stockpay)
            if mod_name in sys.modules:
                mod_file = str(getattr(sys.modules[mod_name], "__file__", "") or "")
                if "stockpay" in mod_file.replace("\\", "/"):
                    errors.append(f"{mod_name}:{attr} → ignoré (module stockpay)")
                    continue
            mod = importlib.import_module(mod_name)
            mod_file = str(getattr(mod, "__file__", "") or "")
            if mod_file and "aquaviva" not in mod_file.replace("\\", "/"):
                # module trouvé hors ~/aquaviva → pas le bon
                if AQUAVIVA_DIR.name not in mod_file.replace("\\", "/"):
                    errors.append(
                        f"{mod_name}:{attr} → fichier hors aquaviva ({mod_file})"
                    )
                    continue
            obj = getattr(mod, attr)
            if obj is stockpay_app:
                errors.append(f"{mod_name}:{attr} → même objet que Stockpay")
                continue
            return obj
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{mod_name}:{attr} → {exc}")
    raise ImportError(
        "Impossible de charger aquaviva. "
        "Ajoute dans ~/stockpay/.env par ex. "
        "AQUAVIVA_IMPORT=booking_engine:app\n" + "\n".join(errors)
    )


aquaviva_app = _load_aquaviva()
if aquaviva_app is stockpay_app:
    raise RuntimeError(
        "Aquaviva a chargé Stockpay par erreur. "
        "Définis AQUAVIVA_IMPORT dans ~/stockpay/.env"
    )


def _configure_mounted_flask(flask_app, mount_path: str) -> None:
    """Préfixe url_for / cookies sous DispatcherMiddleware (SCRIPT_NAME)."""
    try:
        flask_app.config["APPLICATION_ROOT"] = mount_path
        # Cookies isolés par app montée (évite collision Stockpay ↔ Aquaviva)
        flask_app.config["SESSION_COOKIE_PATH"] = mount_path
        # Nom distinct pour Aquaviva si cookie path seul ne suffit pas
        if mount_path == "/aquaviva":
            flask_app.config.setdefault("SESSION_COOKIE_NAME", "aquaviva_session")
    except Exception:
        pass


_configure_mounted_flask(stockpay_app, "/stockpay")
_configure_mounted_flask(aquaviva_app, "/aquaviva")


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

# ProxyFix à l'extérieur ; DispatcherMiddleware pose déjà SCRIPT_NAME=/aquaviva|/stockpay
application = ProxyFix(application, x_for=1, x_proto=1, x_host=1, x_prefix=1)
