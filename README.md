# Stockpay

Interface de paiement pour l’hébergement mutualisé (disque, webapp, RAM).
**Stockpay** — Fait par **webbap**.

## Fonctionnalités

- Liste des espaces avec taille réelle + tarif
- Sync disque (`du`) → facturation en Go (arrondi supérieur) → tarif auto
- E-mail par projet (admin)
- Avis d’impayé + rappels (délai configurable, défaut 7 jours)
- Page de paiement par projet
- Commandes CLI pour cron / scheduled tasks PythonAnywhere

## Stripe (carte bancaire)

1. Créez un compte sur [Stripe](https://stripe.com) (gratuit, frais uniquement par paiement).
2. Copiez les clés **test** puis **live** dans `.env` :
   - `STRIPE_SECRET_KEY=sk_…`
   - `STRIPE_PUBLISHABLE_KEY=pk_…` (optionnel pour Checkout redirect)
3. Webhook (recommandé en prod) : endpoint `https://votre-domaine/webhook/stripe`
   événement `checkout.session.completed` → `STRIPE_WEBHOOK_SECRET=whsec_…`
4. Sur la page paiement : bouton **Payer par carte** → page Stripe sécurisée.
   Le mode manuel (Lydia / virement) reste disponible si `STRIPE_ALLOW_MANUAL=true`.

## Factures

Après paiement, bouton **Générer une facture** (page succès, page paiement, ou admin).
Facture HTML avec lien privé + **Imprimer / PDF** (aucune dépendance payante).
Personnalisez `INVOICE_ISSUER_NAME`, `INVOICE_ISSUER_DETAILS`, `INVOICE_FOOTER` dans le `.env`.

## Tarifs

Tu saisis ton coût PythonAnywhere découpé en 3 postes, puis le **% à facturer** :

| Poste | Défaut | Répartition |
|-------|--------|-------------|
| Disque | 4,00 € | au prorata des Go |
| Webapp | 3,50 € | parts égales |
| RAM / CPU | 2,50 € | parts égales |
| % à facturer | 100 % | ex. 80 % = tu absorbs 20 % |

Modifiable dans l’admin (recalcul immédiat) ou via `.env` au premier démarrage.

## Lancer en local

```bash
cd ~/stockpay
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis éditer
python app.py
```

- Public : http://127.0.0.1:5000  
- Admin : http://127.0.0.1:5000/admin (mot de passe `STOCKPAY_ADMIN_PASSWORD`)

## Synchroniser les tailles

Dans l’admin : bouton **Synchroniser**, ou en CLI :

```bash
export FLASK_APP=app.py
flask sync-storage
```

Sur PythonAnywhere, `STOCKPAY_SCAN_ROOT` doit pointer vers le home
(ex. `/home/votreuser`) où se trouvent `aquaviva/`, `cle_corse/`, `stockpay/`.
Le dossier `stockpay` est exclu du scan.

## Rappels e-mail

```bash
flask send-reminders
```

Sans SMTP configuré, les mails sont **simulés** dans les logs (pratique en local).
Avec Gmail : mot de passe d’application + variables `MAIL_*` du `.env`.

Planifier sur PythonAnywhere (Scheduled tasks), par ex. chaque jour :

```bash
cd ~/stockpay && source .venv/bin/activate && flask sync-storage && flask send-reminders
```

## Déploiement PythonAnywhere

1. Placez le projet dans `~/stockpay` à côté des autres dossiers.
2. Virtualenv + `pip install -r requirements.txt`.
3. WSGI → fichier `wsgi.py` du projet (`application`).
4. Créez `.env` depuis `.env.example` (`SECRET_KEY`, `STOCKPAY_ADMIN_PASSWORD`, `STOCKPAY_SCAN_ROOT`).
5. Renseignez `PUBLIC_BASE_URL=https://votreuser.pythonanywhere.com`.
6. **Ensuite seulement** : clés Stripe live + webhook (voir admin → « Circuit paiement »).

## Ajouter un nouveau dossier hébergé

Après avoir créé le dossier sur PythonAnywhere :

```bash
cd ~/stockpay && source .venv/bin/activate
flask list-untracked
flask add-project mon_nouveau_dossier --email client@exemple.com --name "Mon site"
# ou synchroniser tous les dossiers d’un coup :
flask sync-storage
```

Aussi possible dans **/admin** → « Ajouter un projet / dossier ».

Le paiement ne marque « payé » qu’après **vérification Stripe** (pas de confirmation manuelle).
