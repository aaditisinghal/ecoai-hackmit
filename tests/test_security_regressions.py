"""Regression tests for the vulnerabilities found in the pre-2.0 code.

One test per finding. If any of these ever fail, a specific historical
security defect has come back.
"""

from __future__ import annotations

import hashlib

import pytest

from ecoai.extensions import db
from ecoai.models import User
from ecoai.services.credentials import hash_password, verify_password
from tests.conftest import TEST_PASSWORD


class TestDashboardAccessControl:
    """The dashboard had its auth check commented out and no user filter."""

    def test_dashboard_requires_authentication(self, client):
        response = client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_dashboard_never_shows_another_users_receipts(
        self, client, make_user, make_receipts
    ):
        alice, _ = make_user("alice")
        bob, _ = make_user("bob")
        make_receipts(alice, count=3)
        make_receipts(bob, count=7)

        client.post("/login", data={"identifier": "bob", "password": TEST_PASSWORD})
        body = client.get("/dashboard").get_data(as_text=True)

        # Bob has 7 receipts; the whole table has 10. Seeing 10 would mean the
        # query lost its WHERE clause again.
        assert f"rcpt-{bob.id}-0-0" in body
        assert f"rcpt-{alice.id}-0-0" not in body


class TestEmailReportIsNotAnOpenRelay:
    """/send-stats-email accepted any address from an unauthenticated form."""

    def test_report_requires_authentication(self, client):
        response = client.post("/dashboard/report", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_report_ignores_any_supplied_recipient(self, auth_client, user, make_receipts, app):
        make_receipts(user, count=2)

        sent: list = []
        app.extensions["ecoai_mailer"].send = lambda message: sent.append(message) or True

        auth_client.post(
            "/dashboard/report",
            data={"email": "attacker@evil.example", "recipient": "attacker@evil.example"},
            follow_redirects=True,
        )

        assert len(sent) == 1
        assert sent[0].to == user.email
        assert "evil.example" not in sent[0].to


class TestAdminAccessControl:
    """Admin was gated by a hardcoded username and password in source."""

    def test_admin_rejects_anonymous(self, client):
        for path in ("/admin/", "/admin/users", "/admin/receipts"):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 302, path
            assert "/login" in response.headers["Location"]

    def test_admin_rejects_non_admin_user(self, auth_client):
        for path in ("/admin/", "/admin/users", "/admin/receipts"):
            assert auth_client.get(path).status_code == 403, path

    def test_legacy_admin_credentials_do_not_exist(self, client):
        """The old pair must not authenticate anywhere."""
        response = client.post(
            "/login",
            data={"identifier": "admin", "password": "ecoai_admin_2024"},
            follow_redirects=False,
        )
        assert response.status_code == 401

    def test_no_legacy_admin_routes(self, client):
        for path in ("/admin/auth", "/admin/login", "/admin/dashboard", "/admin/logout"):
            assert client.get(path).status_code in (404, 405), path

    def test_admin_user_list_cannot_expose_api_keys(self, admin_client, make_user):
        _, secret = make_user("someone-else")
        body = admin_client.get("/admin/users").get_data(as_text=True)
        assert secret not in body
        # Only the display prefix may appear.
        assert secret[:14] in body


class TestApiKeyStorage:
    """Keys were stored in cleartext and rendered on the profile page."""

    def test_key_is_never_stored_in_cleartext(self, user):
        assert user.api_key_hash != user.api_key_secret
        assert user.api_key_hash == hashlib.sha256(user.api_key_secret.encode()).hexdigest()
        assert len(user.api_key_hash) == 64

    def test_profile_shows_only_the_prefix(self, auth_client, user):
        body = auth_client.get("/profile").get_data(as_text=True)
        assert user.api_key_secret not in body
        assert user.api_key_prefix in body

    def test_rotation_invalidates_the_previous_key(self, auth_client, user, client):
        old_secret = user.api_key_secret

        auth_client.post("/profile/api-key/rotate", follow_redirects=True)

        response = client.get("/api/v1/me", headers={"X-API-Key": old_secret})
        assert response.status_code == 401


class TestPasswordHashing:
    """Passwords were unsalted SHA-256."""

    def test_new_passwords_use_a_slow_salted_kdf(self):
        digest = hash_password("some-password-value")
        assert digest != hashlib.sha256(b"some-password-value").hexdigest()
        assert "$" in digest, "expected a method$salt$hash structure"
        assert hash_password("same") != hash_password("same"), "hash must be salted"

    def test_legacy_sha256_still_verifies(self):
        legacy = hashlib.sha256(b"old-password").hexdigest()
        assert verify_password(legacy, "old-password") is True
        assert verify_password(legacy, "wrong") is False

    def test_legacy_hash_upgrades_on_successful_login(self, client, make_user, app):
        legacy = hashlib.sha256(b"legacy-password-1").hexdigest()
        legacy_user, _ = make_user("legacyuser", password=None, password_hash=legacy)
        assert legacy_user.password_hash == legacy

        response = client.post(
            "/login",
            data={"identifier": "legacyuser", "password": "legacy-password-1"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        refreshed = db.session.get(User, legacy_user.id)
        assert refreshed.password_hash != legacy
        assert "$" in refreshed.password_hash
        assert verify_password(refreshed.password_hash, "legacy-password-1") is True


class TestFakeOAuthRemoved:
    """/auth/google and /auth/apple created accounts with no authentication."""

    def test_apple_route_is_gone(self, client):
        assert client.get("/auth/apple").status_code == 404

    def test_google_route_absent_when_unconfigured(self, client):
        assert client.get("/auth/google").status_code == 404

    def test_no_account_is_created_by_hitting_oauth_urls(self, client, app):
        before = db.session.query(User).count()
        client.get("/auth/google")
        client.get("/auth/apple")
        assert db.session.query(User).count() == before


class TestApiAuthentication:
    def test_missing_key_is_401(self, client):
        assert client.get("/api/v1/me").status_code == 401

    def test_invalid_key_is_401_not_403(self, client):
        """403 for a wrong key told an attacker the key format was right."""
        response = client.get("/api/v1/me", headers={"X-API-Key": "ecoai_definitely-not-a-real-key"})
        assert response.status_code == 401

    def test_deactivated_account_cannot_use_its_key(self, client, make_user, app):
        disabled, secret = make_user("disabled-user", is_active=False)
        response = client.get("/api/v1/me", headers={"X-API-Key": secret})
        assert response.status_code == 401

    def test_receipts_never_leak_internal_ids(self, client, user, make_receipts):
        make_receipts(user, count=2)
        payload = client.get(
            "/api/v1/receipts", headers={"X-API-Key": user.api_key_secret}
        ).get_json()

        assert isinstance(payload["receipts"], list)
        for receipt in payload["receipts"]:
            assert isinstance(receipt, dict), "must be objects, not positional tuples"
            assert "user_id" not in receipt
            assert "id" not in receipt

    def test_one_account_cannot_overwrite_anothers_receipt(self, client, make_user):
        alice, alice_key = make_user("alice2")
        bob, bob_key = make_user("bob2")

        event = {
            "type": "receipt",
            "receipt_id": "shared-id",
            "payload": {"tokens_before": 100, "tokens_after": 50},
        }
        first = client.post(
            "/api/v1/receipts/batch",
            json={"events": [event]},
            headers={"X-API-Key": alice_key},
        )
        assert first.status_code == 200

        second = client.post(
            "/api/v1/receipts/batch",
            json={"events": [event]},
            headers={"X-API-Key": bob_key},
        )
        assert second.status_code == 207
        assert "another account" in second.get_json()["rejected"][0]["reason"]


class TestOpenRedirect:
    def test_login_next_cannot_leave_the_site(self, client, user):
        response = client.post(
            "/login?next=https://evil.example/phish",
            data={"identifier": user.username, "password": TEST_PASSWORD},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "evil.example" not in response.headers["Location"]
        assert response.headers["Location"] == "/dashboard"

    def test_login_next_accepts_relative_paths(self, client, user):
        response = client.post(
            "/login?next=/profile",
            data={"identifier": user.username, "password": TEST_PASSWORD},
            follow_redirects=False,
        )
        assert response.headers["Location"] == "/profile"


class TestUserEnumeration:
    def test_signup_collision_does_not_reveal_which_field(self, client, make_user):
        make_user("taken", email="taken@example.com")

        response = client.post(
            "/signup",
            data={
                "username": "taken",
                "email": "brand-new@example.com",
                "password": "a-long-enough-password",
                "confirm_password": "a-long-enough-password",
            },
        )
        body = response.get_data(as_text=True)
        assert "username or email is already registered" in body


class TestSecurityHeaders:
    def test_baseline_headers_present(self, client):
        headers = client.get("/").headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert "Content-Security-Policy" in headers
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


class TestLogoutIsPost:
    def test_get_logout_is_rejected(self, auth_client):
        """A GET /logout could be triggered by any third-party image tag."""
        assert auth_client.get("/logout").status_code == 405

    def test_post_logout_works(self, auth_client):
        response = auth_client.post("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert auth_client.get("/dashboard", follow_redirects=False).status_code == 302


class TestNoHardcodedSecrets:
    """Nothing in the package may carry a credential."""

    def test_source_tree_is_clean(self):
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parent.parent
        # The Gmail app password that used to sit in email_service.py.
        leaked = re.compile(r"ikec\s+ckqm\s+balh\s+yhbb", re.IGNORECASE)
        admin_password = re.compile(r"ecoai_admin_2024")

        for path in list(root.glob("ecoai/**/*.py")) + list(root.glob("sdk/*.py")):
            text = path.read_text(encoding="utf-8")
            assert not leaked.search(text), f"leaked SMTP password in {path}"
            assert not admin_password.search(text), f"hardcoded admin password in {path}"


@pytest.mark.parametrize(
    "path",
    ["/", "/docs", "/download", "/healthz", "/api/v1/carbon/regions"],
)
def test_public_routes_stay_public(client, path):
    assert client.get(path).status_code == 200
