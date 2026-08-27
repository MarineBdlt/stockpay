"""StockPay — paiement d’espaces de stockage synchronisés via `du`."""

from functools import wraps

import click
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from config import Config
from circuit import circuit_status
from mailer import send_due_reminders, send_payment_notice
from models import (
    create_or_get_invoice,
    get_billing_settings,
    get_invoice_by_token,
    get_invoice_for_project_month,
    get_project,
    init_db,
    list_projects,
    mark_paid,
    mark_unpaid,
    set_display_name,
    set_project_email,
    unpaid_projects,
    update_billing_settings,
)
from payments import (
    create_checkout_session,
    construct_webhook_event,
    retrieve_checkout_session,
    stripe_enabled,
)
from pricing import billable_total, pricing_explanation, total_hosting_cost
from projects import list_untracked_folders, register_project
from storage import sync_storage
from urls import absolute_url, stripe_success_url

app = Flask(__name__)
app.config.from_object(Config)
init_db()

# Dev local derrière rien ; en prod ProxyFix est dans wsgi.py
if Config.PUBLIC_BASE_URL:
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


@app.context_processor
def inject_branding():
    return {
        "app_name": Config.APP_NAME,
        "app_credit": Config.APP_CREDIT,
        "app_tagline": Config.APP_TAGLINE,
    }


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Connexion admin requise.", "error")
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@app.route("/")
def index():
    projects = list_projects(active_only=True)
    settings = get_billing_settings()
    return render_template(
        "index.html",
        projects=projects,
        settings=settings,
        pricing_text=pricing_explanation(settings),
        billable=billable_total(settings),
        hosting_total=total_hosting_cost(settings),
    )


@app.route("/pay/<int:project_id>", methods=["GET", "POST"])
def pay(project_id: int):
    project = get_project(project_id)
    if not project or not project["active"]:
        flash("Projet introuvable.", "error")
        return redirect(url_for("index"))

    use_stripe = stripe_enabled()

    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        if "@" not in email:
            flash("Adresse e-mail invalide.", "error")
            return render_template(
                "checkout.html",
                project=project,
                stripe_enabled=use_stripe,
            )

        if not use_stripe:
            flash(
                "Paiement indisponible : Stripe n’est pas encore configuré.",
                "error",
            )
            return render_template(
                "checkout.html",
                project=project,
                stripe_enabled=False,
            )

        if not project.get("email"):
            set_project_email(project_id, email)

        try:
            checkout = create_checkout_session(
                project=project,
                customer_email=email,
                success_url=stripe_success_url(),
                cancel_url=absolute_url("pay", project_id=project_id),
            )
        except Exception as exc:  # noqa: BLE001
            flash(f"Stripe indisponible : {exc}", "error")
            return render_template(
                "checkout.html",
                project=project,
                stripe_enabled=use_stripe,
            )
        return redirect(checkout.url, code=303)

    return render_template(
        "checkout.html",
        project=project,
        stripe_enabled=use_stripe,
    )


@app.route("/pay/stripe/success")
def stripe_success():
    session_id = request.args.get("session_id", "")
    if not session_id or not stripe_enabled():
        flash("Session Stripe invalide.", "error")
        return redirect(url_for("index"))

    try:
        checkout = retrieve_checkout_session(session_id)
    except Exception as exc:  # noqa: BLE001
        flash(f"Impossible de vérifier le paiement : {exc}", "error")
        return redirect(url_for("index"))

    if checkout.payment_status != "paid":
        flash("Paiement non confirmé.", "error")
        return redirect(url_for("index"))

    project_id = int((checkout.metadata or {}).get("project_id") or 0)
    project = get_project(project_id) if project_id else None
    if not project:
        flash("Projet introuvable après paiement.", "error")
        return redirect(url_for("index"))

    month = (checkout.metadata or {}).get("billing_month")
    mark_paid(project_id, month=month)
    email = checkout.customer_email or project.get("email") or ""
    if email and not project.get("email"):
        set_project_email(project_id, email)

    # Rafraîchir le projet après mark_paid
    project = get_project(project_id) or project
    create_or_get_invoice(
        project, payment_method="stripe", client_email=email, month=month
    )

    session["last_payment"] = {
        "project_id": project_id,
        "project_name": project["display_name"],
        "storage_gb": project["billed_gb"],
        "size_human": project["size_human"],
        "price": project["monthly_price"],
        "email": email,
        "method": "stripe",
    }
    return redirect(url_for("success"))


@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    if not Config.STRIPE_WEBHOOK_SECRET:
        return {"error": "webhook non configuré"}, 400
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    try:
        event = construct_webhook_event(payload, sig)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}, 400

    if event["type"] == "checkout.session.completed":
        data = event["data"]["object"]
        if data.get("payment_status") == "paid":
            project_id = int((data.get("metadata") or {}).get("project_id") or 0)
            if project_id:
                month = (data.get("metadata") or {}).get("billing_month")
                mark_paid(project_id, month=month)
                email = data.get("customer_email")
                project = get_project(project_id)
                if email and project and not project.get("email"):
                    set_project_email(project_id, email)
                    project = get_project(project_id)
                if project:
                    create_or_get_invoice(
                        project,
                        payment_method="stripe",
                        client_email=email,
                        month=month,
                    )
    return {"ok": True}


@app.route("/success")
def success():
    payment = session.get("last_payment")
    if not payment:
        return redirect(url_for("index"))
    invoice = None
    project_id = payment.get("project_id")
    if project_id:
        invoice = get_invoice_for_project_month(int(project_id))
    return render_template("success.html", payment=payment, invoice=invoice)


@app.route("/invoice/generate/<int:project_id>", methods=["POST", "GET"])
def generate_invoice(project_id: int):
    project = get_project(project_id)
    if not project or not project["active"]:
        flash("Projet introuvable.", "error")
        return redirect(url_for("index"))

    is_admin = bool(session.get("is_admin"))
    if not project.get("is_paid_this_month") and not is_admin:
        flash("Une facture n’est disponible qu’après paiement du mois.", "error")
        return redirect(url_for("pay", project_id=project_id))

    last = session.get("last_payment") or {}
    method = last.get("method") if last.get("project_id") == project_id else None
    email = (
        last.get("email")
        if last.get("project_id") == project_id
        else project.get("email")
    )
    invoice = create_or_get_invoice(
        project,
        payment_method=method,
        client_email=email,
        month=project.get("paid_month"),
    )
    return redirect(url_for("view_invoice", token=invoice["public_token"]))


@app.route("/invoice/<token>")
def view_invoice(token: str):
    invoice = get_invoice_by_token(token)
    if not invoice:
        flash("Facture introuvable.", "error")
        return redirect(url_for("index"))
    return render_template(
        "invoice.html",
        invoice=invoice,
        issuer_name=Config.INVOICE_ISSUER_NAME,
        issuer_details=Config.INVOICE_ISSUER_DETAILS,
        invoice_footer=Config.INVOICE_FOOTER,
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password") or ""
        if password == Config.ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Connecté.", "ok")
            nxt = request.args.get("next") or url_for("admin")
            return redirect(nxt)
        flash("Mot de passe incorrect.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("Déconnecté.", "ok")
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin():
    projects = list_projects(active_only=False)
    settings = get_billing_settings()
    return render_template(
        "admin.html",
        projects=projects,
        unpaid=unpaid_projects(),
        scan_root=str(Config.SCAN_ROOT),
        settings=settings,
        pricing_text=pricing_explanation(settings),
        billable=billable_total(settings),
        hosting_total=total_hosting_cost(settings),
        stripe_on=stripe_enabled(),
        circuit=circuit_status(),
        untracked=list_untracked_folders(),
    )


@app.route("/admin/billing", methods=["POST"])
@admin_required
def admin_billing():
    try:
        settings = update_billing_settings(
            cost_disk=request.form.get("cost_disk", 0),
            cost_webapp=request.form.get("cost_webapp", 0),
            cost_ram=request.form.get("cost_ram", 0),
            billing_percent=request.form.get("billing_percent", 100),
        )
    except (TypeError, ValueError):
        flash("Valeurs de facturation invalides.", "error")
        return redirect(url_for("admin"))
    flash(
        f"Facturation mise à jour : {pricing_explanation(settings)} "
        f"Tarifs des projets recalculés.",
        "ok",
    )
    return redirect(url_for("admin"))


@app.route("/admin/projects/add", methods=["POST"])
@admin_required
def admin_add_project():
    folder = (request.form.get("folder_name") or "").strip()
    display = (request.form.get("display_name") or "").strip() or None
    email = (request.form.get("email") or "").strip() or None
    require_dir = request.form.get("require_dir") == "1"
    try:
        project = register_project(
            folder,
            display_name=display,
            email=email,
            require_existing_dir=require_dir,
        )
    except (ValueError, FileNotFoundError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin"))
    flash(
        f"Projet « {project['folder_name']} » ajouté "
        f"({project['size_human']} · {project['monthly_price']:.2f} €/mois).",
        "ok",
    )
    return redirect(url_for("admin"))


@app.route("/admin/sync", methods=["POST"])
@admin_required
def admin_sync():
    summary = sync_storage()
    flash(
        f"Scan OK : {summary['scanned']} dossier(s), "
        f"{summary['deactivated']} désactivé(s). "
        f"Racine : {summary['scan_root']}",
        "ok",
    )
    return redirect(url_for("admin"))


@app.route("/admin/project/<int:project_id>", methods=["POST"])
@admin_required
def admin_update_project(project_id: int):
    project = get_project(project_id)
    if not project:
        flash("Projet introuvable.", "error")
        return redirect(url_for("admin"))

    action = request.form.get("action")
    if action == "save":
        set_display_name(project_id, request.form.get("display_name") or "")
        set_project_email(project_id, request.form.get("email"))
        flash(f"« {project['folder_name']} » mis à jour.", "ok")
    elif action == "mark_unpaid":
        mark_unpaid(project_id)
        flash(f"« {project['folder_name']} » marqué impayé.", "ok")
    elif action == "remind":
        project = get_project(project_id)
        if not project or not project.get("email"):
            flash("Attribuez d’abord un e-mail.", "error")
        else:
            ok, detail = send_payment_notice(
                project, reminder=bool(project.get("last_reminder_at"))
            )
            flash(
                f"Mail {'envoyé' if ok else 'échoué'} ({detail}).",
                "ok" if ok else "error",
            )
    return redirect(url_for("admin"))


@app.route("/admin/reminders", methods=["POST"])
@admin_required
def admin_reminders():
    force = request.form.get("force") == "1"
    results = send_due_reminders(force=force)
    sent = sum(1 for r in results if not r.get("skipped") and r.get("ok"))
    skipped = sum(1 for r in results if r.get("skipped"))
    failed = sum(1 for r in results if not r.get("skipped") and not r.get("ok"))
    flash(
        f"Rappels : {sent} envoyé(s), {skipped} ignoré(s) (délai), {failed} échec(s).",
        "ok" if failed == 0 else "error",
    )
    return redirect(url_for("admin"))


@app.cli.command("sync-storage")
def cli_sync_storage():
    """Lance `du -sh -- */` et met à jour tailles + tarifs."""
    summary = sync_storage()
    print(
        f"Scan {summary['scan_root']}: "
        f"{summary['scanned']} dossiers, "
        f"{summary['deactivated']} désactivés."
    )
    for p in summary["projects"]:
        print(
            f"  - {p['folder_name']}: {p['size_human']} "
            f"→ {p['billed_gb']} Go → {p['monthly_price']:.2f} €/mois"
        )


@app.cli.command("add-project")
@click.argument("folder")
@click.option("--email", default=None, help="E-mail client (rappels)")
@click.option("--name", "display_name", default=None, help="Nom affiché")
@click.option(
    "--require-dir/--allow-missing",
    default=True,
    help="Exiger que le dossier existe sur le disque (défaut: oui)",
)
def cli_add_project(folder, email, display_name, require_dir):
    """Ajoute un dossier hébergé au suivi Stockpay."""
    try:
        project = register_project(
            folder,
            display_name=display_name,
            email=email,
            require_existing_dir=require_dir,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from exc
    print(
        f"OK {project['folder_name']}/ · {project['size_human']} · "
        f"{project['billed_gb']} Go · {project['monthly_price']:.2f} €/mois"
    )


@app.cli.command("list-untracked")
def cli_list_untracked():
    """Liste les dossiers sur le disque pas encore suivis."""
    names = list_untracked_folders()
    if not names:
        print("(aucun dossier non suivi)")
        return
    for name in names:
        print(name)


@app.cli.command("send-reminders")
def cli_send_reminders():
    """Envoie les avis / rappels pour les projets impayés."""
    results = send_due_reminders(force=False)
    for r in results:
        if r.get("skipped"):
            print(f"  skip {r['project']} ({r.get('reason')})")
        else:
            print(
                f"  {'OK' if r['ok'] else 'FAIL'} {r['project']} "
                f"({'rappel' if r.get('reminder') else 'avis'}) — {r.get('detail')}"
            )


if __name__ == "__main__":
    app.run(debug=True)
