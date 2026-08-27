"""Scan disque (équivalent de `du -sh -- */`) et mise à jour des tarifs."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from config import Config
from models import deactivate_missing, recalculate_all_prices, upsert_from_scan


def parse_du_line(line: str) -> tuple[str, str] | None:
    """Parse une ligne `du -sh` → (taille_humaine, nom_dossier)."""
    line = line.strip()
    if not line:
        return None
    # Ex. "132M\taquaviva/" ou "1.1G    cle_corse/"
    match = re.match(r"^([0-9.]+[KMGTPE]?)\s+(.+?)/?\s*$", line, re.IGNORECASE)
    if not match:
        return None
    human, name = match.group(1), match.group(2).rstrip("/")
    # garder uniquement le basename
    name = Path(name).name
    return human, name


def human_to_bytes(human: str) -> int:
    """Convertit 132M / 1.1G en octets (base 1024, comme GNU du)."""
    human = human.strip().upper().replace(",", ".")
    match = re.match(r"^([0-9.]+)([KMGTPE]?)$", human)
    if not match:
        return 0
    value = float(match.group(1))
    unit = match.group(2) or ""
    factors = {
        "": 1,
        "K": 1024,
        "M": 1024**2,
        "G": 1024**3,
        "T": 1024**4,
        "P": 1024**5,
        "E": 1024**6,
    }
    return int(value * factors.get(unit, 1))


def run_du(scan_root: Path | None = None) -> list[tuple[str, str, int]]:
    """
    Exécute `du -sh -- */` dans SCAN_ROOT.
    Retourne [(folder_name, size_human, size_bytes), ...]
    """
    root = Path(scan_root or Config.SCAN_ROOT)
    if not root.is_dir():
        raise FileNotFoundError(f"SCAN_ROOT introuvable : {root}")

    # `du -sh -- */` nécessite le shell pour l’expansion des globs
    result = subprocess.run(
        ["bash", "-lc", "du -sh -- */ 2>/dev/null || true"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    entries: list[tuple[str, str, int]] = []
    for line in result.stdout.splitlines():
        parsed = parse_du_line(line)
        if not parsed:
            continue
        human, name = parsed
        if name.lower() in {d.lower() for d in Config.EXCLUDE_DIRS}:
            continue
        if name.startswith("."):
            continue
        entries.append((name, human, human_to_bytes(human)))
    return entries


def sync_storage(scan_root: Path | None = None) -> dict:
    """Scan + upsert projets + recalcul tarifs. Retourne un résumé."""
    entries = run_du(scan_root)
    present: set[str] = set()
    for folder_name, human, size_bytes in entries:
        present.add(folder_name)
        upsert_from_scan(folder_name, size_bytes, human)
    deactivated = deactivate_missing(present)
    projects = recalculate_all_prices()
    return {
        "scanned": len(entries),
        "deactivated": deactivated,
        "projects": projects,
        "scan_root": str(scan_root or Config.SCAN_ROOT),
    }
