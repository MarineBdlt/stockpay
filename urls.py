"""Helpers d’URL absolues (Stripe + sous-chemin /stockpay)."""

from __future__ import annotations

from urllib.parse import urlparse

from flask import url_for

from config import Config


def _join_base(base: str, path: str) -> str:
    """Évite /stockpay/stockpay/... si url_for inclut déjà le préfixe."""
    base = base.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    base_path = urlparse(base).path.rstrip("/")
    if base_path and (path == base_path or path.startswith(base_path + "/")):
        root = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
        return f"{root}{path}"
    return f"{base}{path}"


def absolute_url(endpoint: str, **values) -> str:
    """Construit une URL absolue ; préfère PUBLIC_BASE_URL si défini."""
    path = url_for(endpoint, **values)
    if Config.PUBLIC_BASE_URL:
        return _join_base(Config.PUBLIC_BASE_URL, path)
    return url_for(endpoint, _external=True, **values)


def stripe_success_url() -> str:
    """Success URL Stripe avec placeholder session_id."""
    if Config.PUBLIC_BASE_URL:
        return (
            _join_base(Config.PUBLIC_BASE_URL, "/pay/stripe/success")
            + "?session_id={CHECKOUT_SESSION_ID}"
        )
    return (
        url_for("stripe_success", _external=True)
        + "?session_id={CHECKOUT_SESSION_ID}"
    )
