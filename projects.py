"""Enregistrement de projets (CLI / admin) + mesure disque."""

from __future__ import annotations

import subprocess
from pathlib import Path

from config import Config
from models import add_project, list_projects
from storage import human_to_bytes, parse_du_line


def measure_folder(folder_name: str, scan_root: Path | None = None) -> tuple[str, int]:
    root = Path(scan_root or Config.SCAN_ROOT)
    path = root / folder_name
    if not path.is_dir():
        return "0", 0
    result = subprocess.run(
        ["du", "-sh", "--", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    parsed = parse_du_line(result.stdout.strip()) if result.stdout else None
    if not parsed:
        return "0", 0
    human, _ = parsed
    return human, human_to_bytes(human)


def register_project(
    folder_name: str,
    *,
    display_name: str | None = None,
    email: str | None = None,
    require_existing_dir: bool = False,
) -> dict:
    folder_name = folder_name.strip().rstrip("/")
    root = Config.SCAN_ROOT
    path = root / folder_name
    if require_existing_dir and not path.is_dir():
        raise FileNotFoundError(
            f"Dossier introuvable : {path} (STOCKPAY_SCAN_ROOT={root})"
        )
    human, size_bytes = measure_folder(folder_name)
    return add_project(
        folder_name,
        display_name=display_name,
        email=email,
        size_bytes=size_bytes,
        size_human=human,
    )


def list_untracked_folders(scan_root: Path | None = None) -> list[str]:
    """Dossiers sur le disque pas encore actifs dans Stockpay."""
    root = Path(scan_root or Config.SCAN_ROOT)
    if not root.is_dir():
        return []
    tracked = {p["folder_name"] for p in list_projects(active_only=True)}
    names = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name.lower() in {d.lower() for d in Config.EXCLUDE_DIRS}:
            continue
        if entry.name not in tracked:
            names.append(entry.name)
    return names
