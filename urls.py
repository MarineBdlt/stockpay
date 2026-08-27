"""Helpers d’URL absolues (Stripe + PythonAnywhere derrière proxy)."""

from __future__ import annotations

from flask import url_for

from config import Config


def absolute_url(endpoint: str, **values) -> str:
    """Construit une URL absolue ; préfère PUBLIC_BASE_URL si défini."""
    path = url_for(endpoint, **values)
    if Config.PUBLIC_BASE_URL:
        return f"{Config.PUBLIC_BASE_URL}{path}"
    return url_for(endpoint, _external=True, **values)


def stripe_success_url() -> str:
    """Success URL Stripe avec placeholder session_id."""
    if Config.PUBLIC_BASE_URL:
        return (
            f"{Config.PUBLIC_BASE_URL}/pay/stripe/success"
            "?session_id={CHECKOUT_SESSION_ID}"
        )
    return (
        url_for("stripe_success", _external=True)
        + "?session_id={CHECKOUT_SESSION_ID}"
    )
