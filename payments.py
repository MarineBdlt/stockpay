"""Paiements Stripe Checkout (carte bancaire hébergée chez Stripe)."""

from __future__ import annotations

from datetime import date
from typing import Any

import stripe

from config import Config


def stripe_enabled() -> bool:
    return bool(Config.STRIPE_SECRET_KEY and Config.STRIPE_SECRET_KEY.startswith("sk_"))


def configure_stripe() -> None:
    if stripe_enabled():
        stripe.api_key = Config.STRIPE_SECRET_KEY


def amount_cents(euros: float) -> int:
    return max(50, int(round(float(euros) * 100)))  # min 0,50 € Stripe


def create_checkout_session(
    *,
    project: dict[str, Any],
    customer_email: str,
    success_url: str,
    cancel_url: str,
) -> stripe.checkout.Session:
    configure_stripe()
    return stripe.checkout.Session.create(
        mode="payment",
        customer_email=customer_email or None,
        success_url=success_url,
        cancel_url=cancel_url,
        line_items=[
            {
                "quantity": 1,
                "price_data": {
                    "currency": "eur",
                    "unit_amount": amount_cents(project["monthly_price"]),
                    "product_data": {
                        "name": f"{Config.APP_NAME} — {project['display_name']}",
                        "description": (
                            f"{Config.APP_CREDIT} · hébergement mensuel "
                            f"({project['folder_name']}/ · "
                            f"{project['size_human']} · {project['billed_gb']} Go)"
                        ),
                    },
                },
            }
        ],
        metadata={
            "project_id": str(project["id"]),
            "folder_name": project["folder_name"],
            "billing_month": date.today().strftime("%Y-%m"),
        },
        payment_intent_data={
            "metadata": {
                "project_id": str(project["id"]),
                "folder_name": project["folder_name"],
            }
        },
    )


def retrieve_checkout_session(session_id: str) -> stripe.checkout.Session:
    configure_stripe()
    return stripe.checkout.Session.retrieve(session_id)


def construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    configure_stripe()
    return stripe.Webhook.construct_event(
        payload, sig_header, Config.STRIPE_WEBHOOK_SECRET
    )
