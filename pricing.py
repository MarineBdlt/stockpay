"""Répartition des coûts PythonAnywhere (disque, webapp, RAM) × pourcentage."""

from __future__ import annotations

from typing import Any


def total_hosting_cost(settings: dict[str, Any]) -> float:
    return float(settings["cost_disk"]) + float(settings["cost_webapp"]) + float(
        settings["cost_ram"]
    )


def billable_total(settings: dict[str, Any]) -> float:
    """Montant total à redistribuer après application du %."""
    pct = float(settings["billing_percent"]) / 100.0
    return round(total_hosting_cost(settings) * pct, 2)


def allocate_project_price(
    billed_gb: int,
    total_gb: int,
    project_count: int,
    settings: dict[str, Any],
) -> dict[str, float]:
    """
    - Disque : au prorata des Go facturés
    - Webapp + RAM : parts égales entre les projets actifs
    - Puis × billing_percent
    """
    pct = float(settings["billing_percent"]) / 100.0
    disk_pool = float(settings["cost_disk"]) * pct
    shared_pool = (float(settings["cost_webapp"]) + float(settings["cost_ram"])) * pct

    if project_count <= 0:
        return {
            "price_disk": 0.0,
            "price_shared": 0.0,
            "monthly_price": 0.0,
        }

    if total_gb <= 0 or billed_gb <= 0:
        disk_part = 0.0
    else:
        disk_part = disk_pool * (billed_gb / total_gb)

    shared_part = shared_pool / project_count
    monthly = round(disk_part + shared_part, 2)
    return {
        "price_disk": round(disk_part, 2),
        "price_shared": round(shared_part, 2),
        "monthly_price": monthly,
    }


def pricing_explanation(settings: dict[str, Any]) -> str:
    total = total_hosting_cost(settings)
    billable = billable_total(settings)
    return (
        f"Coût hébergeur {total:.2f} € "
        f"(disque {float(settings['cost_disk']):.2f} € + "
        f"webapp {float(settings['cost_webapp']):.2f} € + "
        f"RAM {float(settings['cost_ram']):.2f} €) "
        f"× {float(settings['billing_percent']):.0f} % = {billable:.2f} € à répartir "
        f"(disque au prorata des Go, webapp+RAM à parts égales)."
    )
