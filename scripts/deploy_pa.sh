#!/bin/bash
# Déploiement Stockpay + aquaviva sous /stockpay et /aquaviva
# Usage (console Bash PythonAnywhere) :
#   bash ~/stockpay/scripts/deploy_pa.sh
set -euo pipefail

USER_PA="$(whoami)"
HOME_PA="/home/${USER_PA}"
STOCKPAY="${HOME_PA}/stockpay"
AQUAVIVA="${HOME_PA}/aquaviva"

echo "==> User: ${USER_PA}"

if [ ! -d "${STOCKPAY}" ]; then
  echo "==> Clone du repo…"
  cd "${HOME_PA}"
  git clone https://github.com/MarineBdlt/stockpay.git
fi

cd "${STOCKPAY}"
echo "==> git pull…"
git pull origin main || true

# Virtualenv
if [ ! -d .venv ]; then
  echo "==> Création venv…"
  python3 -m venv .venv || python3.10 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# .env
if [ ! -f .env ]; then
  echo "==> Création .env depuis exemple…"
  cp .env.example .env
  # valeurs de base si fichier tout neuf
  sed -i "s|^STOCKPAY_SCAN_ROOT=.*|STOCKPAY_SCAN_ROOT=${HOME_PA}|" .env || true
fi

set_env () {
  local key="$1"
  local val="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${val}|" .env
  else
    echo "${key}=${val}" >> .env
  fi
}

set_env PUBLIC_BASE_URL "https://${USER_PA}.pythonanywhere.com/stockpay"
set_env APPLICATION_ROOT "/stockpay"
set_env STOCKPAY_SCAN_ROOT "${HOME_PA}"

# Détecte le point d'entrée aquaviva si possible
if [ -d "${AQUAVIVA}" ]; then
  if [ -f "${AQUAVIVA}/flask_app.py" ]; then
    set_env AQUAVIVA_IMPORT "flask_app:app"
  elif [ -f "${AQUAVIVA}/app.py" ]; then
    set_env AQUAVIVA_IMPORT "app:app"
  elif [ -f "${AQUAVIVA}/wsgi.py" ]; then
    set_env AQUAVIVA_IMPORT "wsgi:application"
  fi
  echo "==> Dossier aquaviva trouvé."
  ls "${AQUAVIVA}"/*.py 2>/dev/null | head -20 || true
else
  echo "!! Pas de dossier ~/aquaviva — le chemin /aquaviva échouera jusqu'à ce qu'il existe."
fi

# WSGI cible (fichier que PA doit charger)
WSGI_TARGET="${HOME_PA}/webbap_wsgi.py"
cat > "${WSGI_TARGET}" << EOF
import sys
sys.path.insert(0, "${STOCKPAY}")
from pa_dispatcher import application
EOF
echo "==> WSGI écrit : ${WSGI_TARGET}"

# Smoke import
echo "==> Test import Stockpay…"
python - <<'PY'
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "stockpay"))
os.chdir(Path.home() / "stockpay")
from app import app
print("Stockpay OK", app.name)
PY

echo ""
echo "============================================================"
echo " FAIT CÔTÉ FICHIERS. Il reste 3 clics dans l'onglet Web PA :"
echo "============================================================"
echo "1) Web → ta web app existante"
echo "2) Section « WSGI configuration file » → remplace le contenu par :"
echo ""
cat "${WSGI_TARGET}"
echo ""
echo "   OU pointe le chemin WSGI vers : ${WSGI_TARGET}"
echo ""
echo "3) Static files — ajoute :"
echo "   /stockpay/static/  →  ${STOCKPAY}/static"
if [ -d "${AQUAVIVA}/static" ]; then
  echo "   /aquaviva/static/  →  ${AQUAVIVA}/static"
else
  echo "   /aquaviva/static/  →  (cherche le dossier static d'aquaviva)"
fi
echo ""
echo "4) Virtualenv (si pas déjà) : ${STOCKPAY}/.venv"
echo "5) Bouton vert Reload"
echo ""
echo "URLs :"
echo "  https://${USER_PA}.pythonanywhere.com/stockpay/"
echo "  https://${USER_PA}.pythonanywhere.com/aquaviva/"
echo ""
echo ".env (extrait) :"
grep -E '^(PUBLIC_BASE_URL|APPLICATION_ROOT|STOCKPAY_SCAN_ROOT|AQUAVIVA_IMPORT)=' .env || true
echo "============================================================"
