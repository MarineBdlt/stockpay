"""Accès SQLite pour les projets StockPay."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any, Iterator

from config import Config, bytes_to_billed_gb
from pricing import allocate_project_price


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _month_key(d: date | None = None) -> str:
    d = d or date.today()
    return d.strftime("%Y-%m")


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(Config.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_name TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                email TEXT,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                size_human TEXT NOT NULL DEFAULT '0',
                billed_gb INTEGER NOT NULL DEFAULT 0,
                monthly_price REAL NOT NULL DEFAULT 0,
                price_disk REAL NOT NULL DEFAULT 0,
                price_shared REAL NOT NULL DEFAULT 0,
                paid_month TEXT,
                last_paid_at TEXT,
                last_reminder_at TEXT,
                reminder_count INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS email_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                recipient TEXT NOT NULL,
                subject TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                ok INTEGER NOT NULL DEFAULT 1,
                detail TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS billing_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                cost_disk REAL NOT NULL,
                cost_webapp REAL NOT NULL,
                cost_ram REAL NOT NULL,
                billing_percent REAL NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_token TEXT NOT NULL UNIQUE,
                project_id INTEGER NOT NULL,
                invoice_number TEXT NOT NULL UNIQUE,
                billing_month TEXT NOT NULL,
                client_name TEXT NOT NULL,
                client_email TEXT,
                folder_name TEXT NOT NULL,
                size_human TEXT NOT NULL,
                billed_gb INTEGER NOT NULL,
                amount REAL NOT NULL,
                amount_disk REAL NOT NULL DEFAULT 0,
                amount_shared REAL NOT NULL DEFAULT 0,
                payment_method TEXT,
                issued_at TEXT NOT NULL,
                UNIQUE(project_id, billing_month),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            """
        )
        _ensure_column(conn, "projects", "price_disk", "price_disk REAL NOT NULL DEFAULT 0")
        _ensure_column(
            conn, "projects", "price_shared", "price_shared REAL NOT NULL DEFAULT 0"
        )

        existing = conn.execute(
            "SELECT id FROM billing_settings WHERE id = 1"
        ).fetchone()
        if not existing:
            conn.execute(
                """
                INSERT INTO billing_settings
                (id, cost_disk, cost_webapp, cost_ram, billing_percent, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                (
                    Config.COST_DISK,
                    Config.COST_WEBAPP,
                    Config.COST_RAM,
                    Config.BILLING_PERCENT,
                    _now_iso(),
                ),
            )


def get_billing_settings() -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM billing_settings WHERE id = 1").fetchone()
    if row is None:
        init_db()
        return get_billing_settings()
    return dict(row)


def update_billing_settings(
    cost_disk: float,
    cost_webapp: float,
    cost_ram: float,
    billing_percent: float,
) -> dict[str, Any]:
    cost_disk = max(0.0, float(cost_disk))
    cost_webapp = max(0.0, float(cost_webapp))
    cost_ram = max(0.0, float(cost_ram))
    billing_percent = min(200.0, max(0.0, float(billing_percent)))
    with get_db() as conn:
        conn.execute(
            """
            UPDATE billing_settings
            SET cost_disk = ?, cost_webapp = ?, cost_ram = ?,
                billing_percent = ?, updated_at = ?
            WHERE id = 1
            """,
            (cost_disk, cost_webapp, cost_ram, billing_percent, _now_iso()),
        )
    recalculate_all_prices()
    return get_billing_settings()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    data["is_paid_this_month"] = data.get("paid_month") == _month_key()
    data["needs_payment"] = bool(data.get("email")) and not data["is_paid_this_month"]
    return data


def list_projects(active_only: bool = True) -> list[dict[str, Any]]:
    sql = "SELECT * FROM projects"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY size_bytes DESC, folder_name COLLATE NOCASE"
    with get_db() as conn:
        rows = conn.execute(sql).fetchall()
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]


def get_project(project_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    return row_to_dict(row)


def get_project_by_folder(folder_name: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE folder_name = ?", (folder_name,)
        ).fetchone()
    return row_to_dict(row)


def add_project(
    folder_name: str,
    *,
    display_name: str | None = None,
    email: str | None = None,
    size_bytes: int = 0,
    size_human: str = "0",
) -> dict[str, Any]:
    """Enregistre (ou réactive) un projet par nom de dossier."""
    import re

    folder_name = (folder_name or "").strip().rstrip("/")
    if not folder_name or not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", folder_name):
        raise ValueError(
            "Nom de dossier invalide (lettres, chiffres, . _ - ; max 64)."
        )
    if folder_name.lower() in {d.lower() for d in Config.EXCLUDE_DIRS}:
        raise ValueError(f"Le dossier « {folder_name} » est exclu du suivi.")

    project = upsert_from_scan(folder_name, size_bytes, size_human)
    if display_name:
        set_display_name(project["id"], display_name)
    if email is not None:
        set_project_email(project["id"], email)
    recalculate_all_prices()
    project = get_project(project["id"])
    assert project is not None
    return project


def upsert_from_scan(
    folder_name: str,
    size_bytes: int,
    size_human: str,
) -> dict[str, Any]:
    billed = bytes_to_billed_gb(size_bytes)
    now = _now_iso()
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM projects WHERE folder_name = ?",
            (folder_name,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE projects
                SET size_bytes = ?, size_human = ?, billed_gb = ?,
                    updated_at = ?, active = 1
                WHERE id = ?
                """,
                (size_bytes, size_human, billed, now, existing["id"]),
            )
            project_id = existing["id"]
        else:
            conn.execute(
                """
                INSERT INTO projects (
                    folder_name, display_name, email, size_bytes, size_human,
                    billed_gb, monthly_price, price_disk, price_shared,
                    paid_month, last_paid_at, last_reminder_at, reminder_count,
                    active, updated_at, created_at
                ) VALUES (?, ?, NULL, ?, ?, ?, 0, 0, 0, NULL, NULL, NULL, 0, 1, ?, ?)
                """,
                (folder_name, folder_name, size_bytes, size_human, billed, now, now),
            )
            project_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    return row_to_dict(row)  # type: ignore[return-value]


def recalculate_all_prices() -> list[dict[str, Any]]:
    """Recalcule tous les tarifs actifs selon disque/webapp/RAM × %."""
    settings = get_billing_settings()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, billed_gb FROM projects WHERE active = 1"
        ).fetchall()
        project_count = len(rows)
        total_gb = sum(int(r["billed_gb"]) for r in rows)
        now = _now_iso()
        updated = []
        for row in rows:
            parts = allocate_project_price(
                billed_gb=int(row["billed_gb"]),
                total_gb=total_gb,
                project_count=project_count,
                settings=settings,
            )
            conn.execute(
                """
                UPDATE projects
                SET monthly_price = ?, price_disk = ?, price_shared = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    parts["monthly_price"],
                    parts["price_disk"],
                    parts["price_shared"],
                    now,
                    row["id"],
                ),
            )
        rows = conn.execute(
            "SELECT * FROM projects WHERE active = 1 "
            "ORDER BY size_bytes DESC, folder_name COLLATE NOCASE"
        ).fetchall()
        updated = [row_to_dict(r) for r in rows]
    return updated  # type: ignore[return-value]


def deactivate_missing(present_folders: set[str]) -> int:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, folder_name FROM projects WHERE active = 1"
        ).fetchall()
        count = 0
        for row in rows:
            if row["folder_name"] not in present_folders:
                conn.execute(
                    "UPDATE projects SET active = 0, updated_at = ? WHERE id = ?",
                    (_now_iso(), row["id"]),
                )
                count += 1
    return count


def set_project_email(project_id: int, email: str | None) -> None:
    email = (email or "").strip() or None
    with get_db() as conn:
        conn.execute(
            "UPDATE projects SET email = ?, updated_at = ? WHERE id = ?",
            (email, _now_iso(), project_id),
        )


def set_display_name(project_id: int, display_name: str) -> None:
    display_name = display_name.strip() or "Projet"
    with get_db() as conn:
        conn.execute(
            "UPDATE projects SET display_name = ?, updated_at = ? WHERE id = ?",
            (display_name, _now_iso(), project_id),
        )


def mark_paid(project_id: int, month: str | None = None) -> None:
    month = month or _month_key()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE projects
            SET paid_month = ?, last_paid_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (month, _now_iso(), _now_iso(), project_id),
        )


def mark_unpaid(project_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE projects
            SET paid_month = NULL, updated_at = ?
            WHERE id = ?
            """,
            (_now_iso(), project_id),
        )


def record_reminder(project_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE projects
            SET last_reminder_at = ?, reminder_count = reminder_count + 1,
                updated_at = ?
            WHERE id = ?
            """,
            (_now_iso(), _now_iso(), project_id),
        )


def log_email(
    project_id: int,
    kind: str,
    recipient: str,
    subject: str,
    ok: bool = True,
    detail: str | None = None,
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO email_log (project_id, kind, recipient, subject, sent_at, ok, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, kind, recipient, subject, _now_iso(), 1 if ok else 0, detail),
        )


def unpaid_projects() -> list[dict[str, Any]]:
    month = _month_key()
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM projects
            WHERE active = 1
              AND email IS NOT NULL
              AND email != ''
              AND (paid_month IS NULL OR paid_month != ?)
            ORDER BY folder_name COLLATE NOCASE
            """,
            (month,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]


def _next_invoice_number(conn: sqlite3.Connection, month: str) -> str:
    year_month = month.replace("-", "")
    prefix = f"SP-{year_month}-"
    row = conn.execute(
        "SELECT invoice_number FROM invoices WHERE invoice_number LIKE ? "
        "ORDER BY invoice_number DESC LIMIT 1",
        (f"{prefix}%",),
    ).fetchone()
    if not row:
        return f"{prefix}001"
    try:
        seq = int(str(row["invoice_number"]).rsplit("-", 1)[-1]) + 1
    except ValueError:
        seq = 1
    return f"{prefix}{seq:03d}"


def get_invoice(invoice_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
    return dict(row) if row else None


def get_invoice_by_token(token: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM invoices WHERE public_token = ?", (token,)
        ).fetchone()
    return dict(row) if row else None


def get_invoice_for_project_month(
    project_id: int, month: str | None = None
) -> dict[str, Any] | None:
    month = month or _month_key()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM invoices WHERE project_id = ? AND billing_month = ?",
            (project_id, month),
        ).fetchone()
    return dict(row) if row else None


def create_or_get_invoice(
    project: dict[str, Any],
    *,
    payment_method: str | None = None,
    client_email: str | None = None,
    month: str | None = None,
) -> dict[str, Any]:
    """Génère une facture pour le mois payé (idempotent par projet+mois)."""
    import secrets

    month = month or project.get("paid_month") or _month_key()
    existing = get_invoice_for_project_month(project["id"], month)
    if existing:
        return existing

    email = (client_email or project.get("email") or "").strip() or None
    with get_db() as conn:
        number = _next_invoice_number(conn, month)
        token = secrets.token_urlsafe(16)
        conn.execute(
            """
            INSERT INTO invoices (
                public_token, project_id, invoice_number, billing_month,
                client_name, client_email, folder_name, size_human, billed_gb,
                amount, amount_disk, amount_shared, payment_method, issued_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token,
                project["id"],
                number,
                month,
                project["display_name"],
                email,
                project["folder_name"],
                project["size_human"],
                project["billed_gb"],
                float(project["monthly_price"]),
                float(project.get("price_disk") or 0),
                float(project.get("price_shared") or 0),
                payment_method,
                _now_iso(),
            ),
        )
        invoice_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        row = conn.execute(
            "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
    return dict(row)
