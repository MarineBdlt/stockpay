"""
WSGI entry point — PythonAnywhere / production.

Sur PythonAnywhere → Web → WSGI configuration file, pointe vers ce fichier
et adapte le chemin project_home ci-dessous.
"""

import sys
from pathlib import Path

project_home = Path(__file__).resolve().parent
if str(project_home) not in sys.path:
    sys.path.insert(0, str(project_home))

# Charge le .env avant l’app
from dotenv import load_dotenv

load_dotenv(project_home / ".env")

from werkzeug.middleware.proxy_fix import ProxyFix

from app import app as application

# PythonAnywhere / reverse proxy : schéma HTTPS + host corrects pour Stripe
application.wsgi_app = ProxyFix(
    application.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)
