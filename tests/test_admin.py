"""Admin pages and exports."""

from __future__ import annotations

import csv
import io

from ecoai.extensions import db
from ecoai.models import User


class TestOverview:
    def test_shows_platform_totals(self, admin_client, admin, make_user, make_receipts):
        other, _ = make_user("customer")
        make_receipts(other, count=4)

        body = admin_client.get("/admin/").get_data(as_text=True)
        assert "customer" in body
        assert "120" in body  # 4 x 30 tokens saved

    def test_states_that_keys_are_not_recoverable(self, admin_client):
        body = admin_client.get("/admin/").get_data(as_text=True)
        assert "not visible here" in body


class TestUserManagement:
    def test_lists_users(self, admin_client, make_user):
        make_user("findme", email="findme@example.com")
        body = admin_client.get("/admin/users").get_data(as_text=True)
        assert "findme" in body
        assert "findme@example.com" in body

    def test_search_filters(self, admin_client, make_user):
        make_user("alpha", email="alpha@example.com")
        make_user("beta", email="beta@example.com")

        body = admin_client.get("/admin/users?q=alpha").get_data(as_text=True)
        assert "alpha@example.com" in body
        assert "beta@example.com" not in body

    def test_toggle_active(self, admin_client, make_user, app):
        target, _ = make_user("toggle-me")
        assert target.is_active

        admin_client.post(f"/admin/users/{target.id}/toggle-active", follow_redirects=True)
        assert db.session.get(User, target.id).is_active is False

        admin_client.post(f"/admin/users/{target.id}/toggle-active", follow_redirects=True)
        assert db.session.get(User, target.id).is_active is True

    def test_toggle_admin(self, admin_client, make_user, app):
        target, _ = make_user("promote-me")

        admin_client.post(f"/admin/users/{target.id}/toggle-admin", follow_redirects=True)
        assert db.session.get(User, target.id).is_admin is True

    def test_cannot_deactivate_yourself(self, admin_client, admin, app):
        response = admin_client.post(
            f"/admin/users/{admin.id}/toggle-active", follow_redirects=True
        )
        assert "cannot deactivate your own account" in response.get_data(as_text=True)
        assert db.session.get(User, admin.id).is_active is True

    def test_cannot_demote_yourself(self, admin_client, admin, app):
        """Otherwise the last admin can lock everyone out of the panel."""
        response = admin_client.post(
            f"/admin/users/{admin.id}/toggle-admin", follow_redirects=True
        )
        assert "cannot change your own administrator status" in response.get_data(as_text=True)
        assert db.session.get(User, admin.id).is_admin is True

    def test_unknown_user_is_404(self, admin_client):
        assert admin_client.post("/admin/users/99999/toggle-active").status_code == 404


class TestExports:
    def test_user_export_columns_match_the_header(self, admin_client, make_user):
        """Regression: the old export's header and data columns disagreed."""
        make_user("exported", email="exported@example.com")

        response = admin_client.get("/admin/export/users.csv")
        assert response.status_code == 200

        rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
        row = next(r for r in rows if r["username"] == "exported")

        assert row["email"] == "exported@example.com"
        assert row["is_admin"] == "False"
        assert row["is_active"] == "True"
        assert row["created_at"].startswith("20")

    def test_user_export_uses_public_ids(self, admin_client, make_user):
        exported, _ = make_user("uuid-check")
        rows = list(
            csv.DictReader(
                io.StringIO(admin_client.get("/admin/export/users.csv").get_data(as_text=True))
            )
        )
        row = next(r for r in rows if r["username"] == "uuid-check")
        assert row["id"] == exported.public_id
        assert row["id"] != str(exported.id)

    def test_user_export_never_contains_a_key_or_hash(self, admin_client, make_user):
        _, secret = make_user("keyholder")
        body = admin_client.get("/admin/export/users.csv").get_data(as_text=True)
        assert secret not in body
        assert "api_key" not in body

    def test_receipt_export_columns_match_the_header(self, admin_client, make_user, make_receipts):
        owner, _ = make_user("receipt-owner")
        make_receipts(owner, count=2)

        rows = list(
            csv.DictReader(
                io.StringIO(admin_client.get("/admin/export/receipts.csv").get_data(as_text=True))
            )
        )
        assert len(rows) == 2

        for row in rows:
            assert row["receipt_id"].startswith("rcpt-")
            assert int(row["tokens_saved"]) == int(row["tokens_before"]) - int(row["tokens_after"])
            assert float(row["co2_g_saved"]) > 0

    def test_unknown_dataset_is_404(self, admin_client):
        assert admin_client.get("/admin/export/secrets.csv").status_code == 404

    def test_exports_require_admin(self, auth_client):
        assert auth_client.get("/admin/export/users.csv").status_code == 403


class TestReceiptsPage:
    def test_lists_all_accounts_receipts(self, admin_client, make_user, make_receipts):
        alice, _ = make_user("alice4")
        bob, _ = make_user("bob4")
        make_receipts(alice, count=2)
        make_receipts(bob, count=3)

        body = admin_client.get("/admin/receipts").get_data(as_text=True)
        assert "alice4" in body
        assert "bob4" in body
