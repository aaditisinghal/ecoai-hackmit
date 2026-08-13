"""Importing a pre-2.0 database.

Builds legacy SQLite files in both historical column orderings, since the old
``init_db`` produced one layout on a fresh database and a different one after
its ``ALTER TABLE`` calls ran against an existing file.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from ecoai.extensions import db
from ecoai.migration.legacy_import import import_legacy_database
from ecoai.models import Receipt, User
from ecoai.services.credentials import hash_api_key, verify_password

LEGACY_API_KEY = "ecoai_test_fixture_legacy_key_00112233"
LEGACY_PASSWORD = "old-password"


def _build_legacy_db(path, *, oauth_columns_before_created_at: bool):
    """Write a legacy database in one of the two historical column orders."""
    connection = sqlite3.connect(path)

    if oauth_columns_before_created_at:
        users_ddl = """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                api_key TEXT UNIQUE NOT NULL,
                oauth_provider TEXT,
                oauth_id TEXT,
                created_at TIMESTAMP
            )
        """
    else:
        users_ddl = """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                api_key TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP,
                oauth_provider TEXT,
                oauth_id TEXT
            )
        """

    connection.execute(users_ddl)
    connection.execute("""
        CREATE TABLE receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_id TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            tokens_before INTEGER NOT NULL,
            tokens_after INTEGER NOT NULL,
            kwh_before REAL, kwh_after REAL,
            co2_g_before REAL, co2_g_after REAL,
            quality_score REAL, model TEXT, region TEXT,
            optimizations_applied TEXT, timestamp TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE TABLE ml_learning_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, optimization_id TEXT, timestamp INTEGER,
            prompt_features TEXT, optimization_result TEXT,
            quality_metrics TEXT, user_feedback TEXT, created_at TIMESTAMP
        )
    """)

    connection.execute(
        "INSERT INTO users (username, email, password_hash, api_key, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "krishna_bhatnagar",
            "krishna@example.com",
            hashlib.sha256(LEGACY_PASSWORD.encode()).hexdigest(),
            LEGACY_API_KEY,
            "2025-09-13 22:39:58",
        ),
    )
    connection.execute(
        "INSERT INTO receipts (receipt_id, user_id, tokens_before, tokens_after, "
        "kwh_before, kwh_after, co2_g_before, co2_g_after, quality_score, model, "
        "region, optimizations_applied, timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "receipt_1757804638_0_ff866785", 1, 22, 13,
            6.1e-06, 3.6e-06, 0.0021, 0.0012, 0.95, "gpt-4",
            "us-east-1", json.dumps(["Removed 'please'"]), "2025-09-13 19:18:10",
        ),
    )
    connection.execute(
        "INSERT INTO ml_learning_data (user_id, optimization_id, timestamp, "
        "prompt_features, optimization_result, quality_metrics, user_feedback) "
        "VALUES (?,?,?,?,?,?,?)",
        (1, "opt-legacy-1", 1757804638000, json.dumps({"length": 22}), "{}", "{}", None),
    )

    connection.commit()
    connection.close()


@pytest.fixture(params=[True, False], ids=["oauth-cols-first", "created-at-first"])
def legacy_db(tmp_path, request):
    path = tmp_path / "ecoai_portal.db"
    _build_legacy_db(path, oauth_columns_before_created_at=request.param)
    return str(path)


class TestImport:
    def test_imports_users_and_receipts(self, app, legacy_db):
        report = import_legacy_database(legacy_db)

        assert report.users_created == 1
        assert report.receipts_created == 1
        assert report.ml_events_created == 1

        user = db.session.query(User).one()
        assert user.username == "krishna_bhatnagar"
        assert user.email == "krishna@example.com"

    def test_reads_by_column_name_not_position(self, app, legacy_db):
        """Both historical column orderings must produce the same result.

        The old code indexed rows positionally, so ``user[5]`` meant
        created_at in one layout and oauth_provider in the other.
        """
        import_legacy_database(legacy_db)

        user = db.session.query(User).one()
        assert user.created_at.year == 2025
        assert user.oauth_provider is None

    def test_legacy_api_key_still_authenticates(self, app, legacy_db, client):
        import_legacy_database(legacy_db)

        user = db.session.query(User).one()
        assert user.api_key_hash == hash_api_key(LEGACY_API_KEY)
        assert user.api_key_prefix == LEGACY_API_KEY[:14]

        response = client.get("/api/v1/me", headers={"X-API-Key": LEGACY_API_KEY})
        assert response.status_code == 200

    def test_legacy_password_still_works_and_then_upgrades(self, app, legacy_db, client):
        import_legacy_database(legacy_db)

        user = db.session.query(User).one()
        assert verify_password(user.password_hash, LEGACY_PASSWORD) is True

        response = client.post(
            "/login",
            data={"identifier": "krishna_bhatnagar", "password": LEGACY_PASSWORD},
            follow_redirects=False,
        )
        assert response.status_code == 302

        refreshed = db.session.get(User, user.id)
        assert "$" in refreshed.password_hash, "hash should have been upgraded"

    def test_quality_score_maps_to_retention_score(self, app, legacy_db):
        import_legacy_database(legacy_db)
        receipt = db.session.query(Receipt).one()
        assert receipt.retention_score == pytest.approx(0.95)

    def test_receipt_fields_are_carried_across(self, app, legacy_db):
        import_legacy_database(legacy_db)

        receipt = db.session.query(Receipt).one()
        assert receipt.receipt_id == "receipt_1757804638_0_ff866785"
        assert receipt.tokens_before == 22
        assert receipt.tokens_after == 13
        assert receipt.model == "gpt-4"
        assert receipt.optimizations_applied == ["Removed 'please'"]
        assert receipt.created_at.year == 2025

    def test_import_is_idempotent(self, app, legacy_db):
        import_legacy_database(legacy_db)
        second = import_legacy_database(legacy_db)

        assert second.users_created == 0
        assert second.users_skipped == 1
        assert second.receipts_created == 0
        assert db.session.query(User).count() == 1
        assert db.session.query(Receipt).count() == 1

    def test_dry_run_writes_nothing(self, app, legacy_db):
        report = import_legacy_database(legacy_db, dry_run=True)

        assert report.users_created == 1  # what it would have done
        assert db.session.query(User).count() == 0
        assert db.session.query(Receipt).count() == 0

    def test_report_renders(self, app, legacy_db):
        rendered = import_legacy_database(legacy_db).render()
        assert "users created" in rendered
        assert "receipts created" in rendered


class TestPartialDatabases:
    def test_missing_tables_are_reported_not_fatal(self, app, tmp_path):
        path = tmp_path / "empty.db"
        sqlite3.connect(path).close()

        report = import_legacy_database(str(path))
        assert report.users_created == 0
        assert any("No users table" in warning for warning in report.warnings)

    def test_orphaned_receipt_is_skipped_with_a_warning(self, app, tmp_path):
        path = tmp_path / "orphan.db"
        _build_legacy_db(path, oauth_columns_before_created_at=False)

        connection = sqlite3.connect(path)
        connection.execute(
            "INSERT INTO receipts (receipt_id, user_id, tokens_before, tokens_after) "
            "VALUES ('orphan', 999, 10, 5)"
        )
        connection.commit()
        connection.close()

        report = import_legacy_database(str(path))
        assert report.receipts_skipped == 1
        assert any("owner was not imported" in warning for warning in report.warnings)
