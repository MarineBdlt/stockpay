#!/bin/bash
# À coller dans une console Bash PythonAnywhere (une seule web app, 2 chemins).
set -e
cd ~/stockpay
git pull origin main || true

USER_PA="$(whoami)"

# .env : URL sous /stockpay
if [ -f .env ]; then
  grep -q '^PUBLIC_BASE_URL=' .env \
    && sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://${USER_PA}.pythonanywhere.com/stockpay|" .env \
    || echo "PUBLIC_BASE_URL=https://${USER_PA}.pythonanywhere.com/stockpay" >> .env
  grep -q '^APPLICATION_ROOT=' .env \
    && sed -i 's|^APPLICATION_ROOT=.*|APPLICATION_ROOT=/stockpay|' .env \
    || echo "APPLICATION_ROOT=/stockpay" >> .env
else
  echo "Pas de .env — crée-le d'abord."
  exit 1
fi

echo "=== Contenu WSGI à coller dans l'onglet Web (fichier WSGI) ==="
cat << EOF
import sys
sys.path.insert(0, "/home/${USER_PA}/stockpay")
from pa_dispatcher import application
EOF

echo ""
echo "=== Static files (onglet Web → Static files) ==="
echo "URL: /stockpay/static/   Directory: /home/${USER_PA}/stockpay/static"
echo "URL: /aquaviva/static/   Directory: /home/${USER_PA}/aquaviva/static   # adapte si besoin"
echo ""
echo "URLs finales :"
echo "  https://${USER_PA}.pythonanywhere.com/stockpay/"
echo "  https://${USER_PA}.pythonanywhere.com/aquaviva/"
echo ""
echo "Si aquaviva ne charge pas, trouve le module Flask :"
echo "  ls ~/aquaviva/*.py"
echo "puis dans .env Stockpay :"
echo "  AQUAVIVA_IMPORT=flask_app:app"
echo "  (ou app:app selon le fichier)"
grep -E 'PUBLIC_BASE_URL|APPLICATION_ROOT' .env
