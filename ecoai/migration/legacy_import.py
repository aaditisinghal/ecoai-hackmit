"""Import a pre-2.0 ``ecoai_portal.db`` into the current schema.

Two details matter for continuity:

*API keys keep working.* The old schema stored them in cleartext, so the
plaintext is available here and can be hashed into the new column. Every key
that worked before this import still works after it, and none of them are
recoverable from the database afterwards.

*Passwords are not re-derived.* The old scheme was an unsalted SHA-256 digest
and the cleartext is unavailable, so the digest is carried across verbatim.
:func:`ecoai.services.credentials.verify_password` recognises the legacy
format, and the account is upgraded to scrypt the first time its owner
successfully signs in.

The legacy schema exists in two column orderings depending on when the
database was created - ``created_at`` sits at index 5 in one and index 7 in the
other - so every read here is by column name.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from ecoai.extensions import db
from ecoai.models import MlLearningEvent, MlPerformanceSnapshot, Receipt, User
from ecoai.services.credentials import API_KEY_DISPLAY_CHARS, hash_api_key

logger = logging.getLogger(__name__)


@dataclass
class ImportReport:
    users_created: int = 0
    users_skipped: int = 0
    receipts_created: int = 0
    receipts_skipped: int = 0
    ml_events_created: int = 0
    ml_snapshots_created: int = 0
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            "Legacy import summary",
            f"  users created:      {self.users_created}",
            f"  users skipped:      {self.users_skipped} (already present)",
            f"  receipts created:   {self.receipts_created}",
            f"  receipts skipped:   {self.receipts_skipped} (already present)",
            f"  ml events created:  {self.ml_events_created}",
            f"  ml snapshots:       {self.ml_snapshots_created}",
        ]
        if self.warnings:
            lines.append("  warnings:")
            lines.extend(f"    - {warning}" for warning in self.warnings)
        return "\n".join(lines)


def import_legacy_database(sqlite_path: str | Path, *, dry_run: bool = False) -> ImportReport:
    """Copy accounts, receipts and telemetry out of a legacy database."""
    report = ImportReport()

    connection = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row

    try:
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

        legacy_to_new_user_id = _import_users(connection, tables, report)
        _import_receipts(connection, tables, legacy_to_new_user_id, report)
        _import_ml_tables(connection, tables, legacy_to_new_user_id, report)

        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    finally:
        connection.close()

    return report


def _import_users(
    connection: sqlite3.Connection, tables: set[str], report: ImportReport
) -> dict[int, int]:
    """Return a mapping from legacy user id to new user id."""
    mapping: dict[int, int] = {}
    if "users" not in tables:
        report.warnings.append("No users table found.")
        return mapping

    columns = _columns(connection, "users")

    for row in connection.execute("SELECT * FROM users"):
        legacy_id = row["id"]
        email = (_get(row, columns, "email") or "").strip().lower()
        username = (_get(row, columns, "username") or "").strip()

        if not email or not username:
            report.warnings.append(f"Skipped legacy user id={legacy_id}: missing username or email.")
            continue

        existing = db.session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing is not None:
            mapping[legacy_id] = existing.id
            report.users_skipped += 1
            continue

        legacy_api_key = _get(row, columns, "api_key")
        user = User(
            username=username,
            email=email,
            # Carried across as-is; upgraded on first successful login.
            password_hash=_get(row, columns, "password_hash"),
            oauth_provider=_get(row, columns, "oauth_provider"),
            oauth_subject=_get(row, columns, "oauth_id"),
            created_at=_parse_datetime(_get(row, columns, "created_at")),
            is_active=True,
            is_admin=False,
        )

        if legacy_api_key:
            user.api_key_hash = hash_api_key(legacy_api_key)
            user.api_key_prefix = legacy_api_key[:API_KEY_DISPLAY_CHARS]
            user.api_key_created_at = user.created_at

        db.session.add(user)
        db.session.flush()

        mapping[legacy_id] = user.id
        report.users_created += 1

    return mapping


def _import_receipts(
    connection: sqlite3.Connection,
    tables: set[str],
    user_ids: dict[int, int],
    report: ImportReport,
) -> None:
    if "receipts" not in tables:
        return

    columns = _columns(connection, "receipts")

    for row in connection.execute("SELECT * FROM receipts"):
        receipt_id = _get(row, columns, "receipt_id")
        if not receipt_id:
            report.receipts_skipped += 1
            continue

        new_user_id = user_ids.get(_get(row, columns, "user_id"))
        if new_user_id is None:
            report.warnings.append(
                f"Skipped receipt {receipt_id}: its owner was not imported."
            )
            report.receipts_skipped += 1
            continue

        already = db.session.execute(
            select(Receipt.id).where(Receipt.receipt_id == receipt_id)
        ).scalar_one_or_none()
        if already is not None:
            report.receipts_skipped += 1
            continue

        db.session.add(
            Receipt(
                receipt_id=receipt_id,
                user_id=new_user_id,
                tokens_before=int(_get(row, columns, "tokens_before") or 0),
                tokens_after=int(_get(row, columns, "tokens_after") or 0),
                kwh_before=float(_get(row, columns, "kwh_before") or 0.0),
                kwh_after=float(_get(row, columns, "kwh_after") or 0.0),
                co2_g_before=float(_get(row, columns, "co2_g_before") or 0.0),
                co2_g_after=float(_get(row, columns, "co2_g_after") or 0.0),
                # The legacy column was named quality_score but only ever held
                # a hardcoded 0.95; it maps onto retention_score.
                retention_score=_optional_float(_get(row, columns, "quality_score")),
                model=_get(row, columns, "model") or None,
                region=_get(row, columns, "region") or None,
                optimizations_applied=_parse_json_list(
                    _get(row, columns, "optimizations_applied")
                ),
                created_at=_parse_datetime(_get(row, columns, "timestamp")),
            )
        )
        report.receipts_created += 1


def _import_ml_tables(
    connection: sqlite3.Connection,
    tables: set[str],
    user_ids: dict[int, int],
    report: ImportReport,
) -> None:
    if "ml_learning_data" in tables:
        columns = _columns(connection, "ml_learning_data")
        for row in connection.execute("SELECT * FROM ml_learning_data"):
            new_user_id = user_ids.get(_get(row, columns, "user_id"))
            if new_user_id is None:
                continue
            db.session.add(
                MlLearningEvent(
                    user_id=new_user_id,
                    optimization_id=str(_get(row, columns, "optimization_id") or "")[:128],
                    prompt_features=_parse_json_dict(_get(row, columns, "prompt_features")),
                    optimization_result=_parse_json_dict(
                        _get(row, columns, "optimization_result")
                    ),
                    quality_metrics=_parse_json_dict(_get(row, columns, "quality_metrics")),
                    user_feedback=_get(row, columns, "user_feedback"),
                    observed_at=_parse_epoch_ms(_get(row, columns, "timestamp")),
                    created_at=_parse_datetime(_get(row, columns, "created_at")),
                )
            )
            report.ml_events_created += 1

    if "ml_performance_metrics" in tables:
        columns = _columns(connection, "ml_performance_metrics")
        for row in connection.execute("SELECT * FROM ml_performance_metrics"):
            new_user_id = user_ids.get(_get(row, columns, "user_id"))
            if new_user_id is None:
                continue
            db.session.add(
                MlPerformanceSnapshot(
                    user_id=new_user_id,
                    total_optimizations=int(_get(row, columns, "total_optimizations") or 0),
                    average_quality=float(_get(row, columns, "average_quality") or 0.0),
                    average_token_reduction=float(
                        _get(row, columns, "average_token_reduction") or 0.0
                    ),
                    success_rate=float(_get(row, columns, "success_rate") or 0.0),
                    quality_trend=float(_get(row, columns, "quality_trend") or 0.0),
                    observed_at=_parse_epoch_ms(_get(row, columns, "timestamp")),
                    created_at=_parse_datetime(_get(row, columns, "created_at")),
                )
            )
            report.ml_snapshots_created += 1


# -- Helpers -----------------------------------------------------------------


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}


def _get(row: sqlite3.Row, columns: set[str], name: str):
    """Read by column name, tolerating columns the legacy schema lacked."""
    return row[name] if name in columns else None


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_json_list(value) -> list:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _parse_json_dict(value) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_datetime(value) -> datetime:
    now = datetime.now(UTC)
    if value is None:
        return now
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, int | float):
        return _parse_epoch_ms(value) or now
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return now
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_epoch_ms(value) -> datetime | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    seconds = numeric / 1000 if numeric > 1e11 else numeric
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None
