"""Signup, login, profile and API key lifecycle."""

from __future__ import annotations

from ecoai.extensions import db
from ecoai.models import User
from ecoai.services.credentials import hash_api_key
from tests.conftest import TEST_PASSWORD


class TestSignup:
    def _payload(self, **overrides):
        payload = {
            "username": "newperson",
            "email": "new@example.com",
            "password": "a-sufficiently-long-password",
            "confirm_password": "a-sufficiently-long-password",
        }
        payload.update(overrides)
        return payload

    def test_creates_an_account_and_signs_in(self, client, app):
        response = client.post("/signup", data=self._payload(), follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["Location"] == "/profile"

        user = db.session.query(User).filter_by(username="newperson").one()
        assert user.email == "new@example.com"
        assert user.has_password
        assert user.has_api_key
        assert not user.is_admin

    def test_shows_the_api_key_exactly_once(self, client, app):
        client.post("/signup", data=self._payload())

        first = client.get("/profile").get_data(as_text=True)
        assert "will not be shown again" in first

        second = client.get("/profile").get_data(as_text=True)
        assert "will not be shown again" not in second

    def test_issued_key_authenticates(self, client, app):
        client.post("/signup", data=self._payload())

        body = client.get("/profile").get_data(as_text=True)
        start = body.index("<code id=\"new-key\">") + len("<code id=\"new-key\">")
        secret = body[start : body.index("</code>", start)].strip()

        assert client.get("/api/v1/me", headers={"X-API-Key": secret}).status_code == 200
        user = db.session.query(User).filter_by(username="newperson").one()
        assert user.api_key_hash == hash_api_key(secret)

    def test_email_is_normalized_to_lowercase(self, client, app):
        client.post("/signup", data=self._payload(email="MixedCase@Example.COM"))
        assert db.session.query(User).filter_by(email="mixedcase@example.com").one()

    def test_mismatched_passwords_are_rejected(self, client, app):
        client.post("/signup", data=self._payload(confirm_password="different-password"))
        assert db.session.query(User).count() == 0

    def test_short_password_is_rejected(self, client, app):
        client.post("/signup", data=self._payload(password="short", confirm_password="short"))
        assert db.session.query(User).count() == 0

    def test_breached_password_is_rejected(self, client, app):
        client.post(
            "/signup", data=self._payload(password="password123", confirm_password="password123")
        )
        assert db.session.query(User).count() == 0

    def test_reserved_usernames_are_rejected(self, client, app):
        client.post("/signup", data=self._payload(username="admin"))
        assert db.session.query(User).count() == 0

    def test_invalid_email_is_rejected(self, client, app):
        client.post("/signup", data=self._payload(email="not-an-email"))
        assert db.session.query(User).count() == 0

    def test_signed_in_user_is_redirected_away(self, auth_client):
        response = auth_client.get("/signup", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["Location"] == "/dashboard"


class TestLogin:
    def test_by_username(self, client, user):
        response = client.post(
            "/login", data={"identifier": user.username, "password": TEST_PASSWORD}
        )
        assert response.status_code == 302

    def test_by_email(self, client, user):
        response = client.post(
            "/login", data={"identifier": user.email, "password": TEST_PASSWORD}
        )
        assert response.status_code == 302

    def test_username_match_is_case_insensitive(self, client, user):
        response = client.post(
            "/login", data={"identifier": user.username.upper(), "password": TEST_PASSWORD}
        )
        assert response.status_code == 302

    def test_wrong_password_is_401(self, client, user):
        response = client.post(
            "/login", data={"identifier": user.username, "password": "wrong-password"}
        )
        assert response.status_code == 401

    def test_unknown_user_is_401(self, client):
        response = client.post(
            "/login", data={"identifier": "ghost", "password": "whatever-password"}
        )
        assert response.status_code == 401

    def test_deactivated_account_is_403(self, client, make_user):
        disabled, _ = make_user("disabled", is_active=False)
        response = client.post(
            "/login", data={"identifier": "disabled", "password": TEST_PASSWORD}
        )
        assert response.status_code == 403

    def test_oauth_only_account_cannot_use_the_password_form(self, client, make_user):
        make_user("oauthonly", password=None)
        response = client.post(
            "/login", data={"identifier": "oauthonly", "password": ""}
        )
        assert response.status_code in (401, 200)

    def test_last_login_is_recorded(self, client, user, app):
        assert user.last_login_at is None
        client.post("/login", data={"identifier": user.username, "password": TEST_PASSWORD})
        assert db.session.get(User, user.id).last_login_at is not None


class TestApiKeyRotation:
    def test_rotation_issues_a_working_new_key(self, auth_client, user, client, app):
        old = user.api_key_secret

        auth_client.post("/profile/api-key/rotate", follow_redirects=False)
        body = auth_client.get("/profile").get_data(as_text=True)

        start = body.index("<code id=\"new-key\">") + len("<code id=\"new-key\">")
        new_secret = body[start : body.index("</code>", start)].strip()

        assert new_secret != old
        assert client.get("/api/v1/me", headers={"X-API-Key": new_secret}).status_code == 200
        assert client.get("/api/v1/me", headers={"X-API-Key": old}).status_code == 401

    def test_rotation_requires_authentication(self, client):
        response = client.post("/profile/api-key/rotate", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


class TestPasswordChange:
    def test_changes_the_password(self, auth_client, user, client, app):
        response = auth_client.post(
            "/profile/password",
            data={
                "current_password": TEST_PASSWORD,
                "new_password": "a-brand-new-long-password",
                "confirm_password": "a-brand-new-long-password",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        auth_client.post("/logout")
        assert (
            client.post(
                "/login",
                data={"identifier": user.username, "password": "a-brand-new-long-password"},
            ).status_code
            == 302
        )

    def test_wrong_current_password_changes_nothing(self, auth_client, user, app):
        original = user.password_hash
        auth_client.post(
            "/profile/password",
            data={
                "current_password": "not-the-right-one",
                "new_password": "a-brand-new-long-password",
                "confirm_password": "a-brand-new-long-password",
            },
        )
        assert db.session.get(User, user.id).password_hash == original


class TestProfilePage:
    def test_requires_authentication(self, client):
        response = client.get("/profile", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_shows_account_details(self, auth_client, user):
        body = auth_client.get("/profile").get_data(as_text=True)
        assert user.username in body
        assert user.email in body
