"""Mailer behaviour, CSRF on the session API path, and CLI commands."""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from ecoai.config import MailConfig
from ecoai.extensions import db
from ecoai.models import User
from ecoai.services.mailer import Mailer, MailError, Message


def _config(**overrides) -> MailConfig:
    base = {
        "enabled": True,
        "host": "smtp.example.com",
        "port": 587,
        "use_tls": True,
        "username": "sender@example.com",
        "password": "app-password",
        "from_email": "noreply@example.com",
        "from_name": "EcoAI Portal",
    }
    base.update(overrides)
    return MailConfig(**base)


@pytest.fixture
def message() -> Message:
    return Message(
        to="user@example.com",
        subject="Your report",
        text_body="plain text",
        html_body="<p>html</p>",
    )


class TestDisabledMailer:
    def test_disabled_mailer_does_not_connect(self, message):
        mailer = Mailer(_config(enabled=False))
        with patch("smtplib.SMTP") as smtp:
            assert mailer.send(message) is True
            smtp.assert_not_called()

    def test_enabled_flag_is_exposed(self):
        assert Mailer(_config(enabled=False)).enabled is False
        assert Mailer(_config(enabled=True)).enabled is True


class TestSmtpDelivery:
    def test_starttls_flow(self, message):
        mailer = Mailer(_config(port=587, use_tls=True))
        with patch("smtplib.SMTP") as smtp:
            server = smtp.return_value.__enter__.return_value
            assert mailer.send(message) is True

            smtp.assert_called_once_with("smtp.example.com", 587, timeout=20)
            server.starttls.assert_called_once()
            server.login.assert_called_once_with("sender@example.com", "app-password")
            server.send_message.assert_called_once()

    def test_implicit_tls_on_port_465(self, message):
        mailer = Mailer(_config(port=465))
        with patch("smtplib.SMTP_SSL") as smtp_ssl, patch("smtplib.SMTP") as smtp:
            assert mailer.send(message) is True
            smtp_ssl.assert_called_once()
            smtp.assert_not_called()

    def test_starttls_is_skipped_when_disabled(self, message):
        mailer = Mailer(_config(use_tls=False))
        with patch("smtplib.SMTP") as smtp:
            mailer.send(message)
            smtp.return_value.__enter__.return_value.starttls.assert_not_called()

    def test_smtp_failure_raises_mailerror(self, message):
        mailer = Mailer(_config())
        with (
            patch("smtplib.SMTP", side_effect=smtplib.SMTPException("refused")),
            pytest.raises(MailError, match="user@example.com"),
        ):
            mailer.send(message)

    def test_network_failure_raises_mailerror(self, message):
        mailer = Mailer(_config())
        with (
            patch("smtplib.SMTP", side_effect=OSError("no route to host")),
            pytest.raises(MailError),
        ):
            mailer.send(message)

    def test_message_carries_both_alternatives(self, message):
        mailer = Mailer(_config())
        captured = MagicMock()
        with patch("smtplib.SMTP") as smtp:
            smtp.return_value.__enter__.return_value.send_message = captured
            mailer.send(message)

        email = captured.call_args[0][0]
        assert email["To"] == "user@example.com"
        assert email["Subject"] == "Your report"
        assert "EcoAI Portal" in email["From"]
        assert {part.get_content_subtype() for part in email.walk()} >= {"plain", "html"}


class TestSessionCsrfOnApi:
    """The API blueprint is CSRF-exempt, so the cookie path validates its own.

    ``WTF_CSRF_ENABLED`` is read per request by both Flask-WTF and
    :func:`ecoai.security._validate_session_csrf`, so it can be switched on
    against the shared app fixture. Building a second application here would
    give it a second in-memory database, leaving the fixtures' users invisible.
    """

    @pytest.fixture(autouse=True)
    def _enable_csrf(self, app):
        app.config["WTF_CSRF_ENABLED"] = True
        yield
        app.config["WTF_CSRF_ENABLED"] = False

    def _sign_in(self, client, username):
        from tests.conftest import TEST_PASSWORD

        page = client.get("/login").get_data(as_text=True)
        marker = 'name="csrf_token" type="hidden" value="'
        token = page.split(marker)[1].split('"')[0]

        response = client.post(
            "/login",
            data={"identifier": username, "password": TEST_PASSWORD, "csrf_token": token},
        )
        assert response.status_code == 302, "sign-in with a valid CSRF token should succeed"

    def test_session_post_without_a_token_is_rejected(self, client, make_user):
        make_user("csrfuser")
        self._sign_in(client, "csrfuser")

        response = client.post("/api/v1/optimize", json={"prompt": "Please summarize."})
        assert response.status_code == 400
        assert response.get_json()["error"] == "csrf_failed"

    def test_session_post_with_a_token_is_accepted(self, client, make_user):
        make_user("csrfuser2")
        self._sign_in(client, "csrfuser2")

        page = client.get("/studio").get_data(as_text=True)
        token = page.split('name="csrf-token" content="')[1].split('"')[0]

        response = client.post(
            "/api/v1/optimize",
            json={"prompt": "Please summarize."},
            headers={"X-CSRFToken": token},
        )
        assert response.status_code == 200

    def test_api_key_post_needs_no_token(self, client, make_user):
        _, secret = make_user("keyuser")

        response = client.post(
            "/api/v1/optimize",
            json={"prompt": "Please summarize."},
            headers={"X-API-Key": secret},
        )
        assert response.status_code == 200


class TestCliCommands:
    def test_create_admin_makes_an_administrator(self, app):
        runner = app.test_cli_runner()
        result = runner.invoke(
            args=[
                "create-admin",
                "--username", "cli-admin",
                "--email", "cli@example.com",
                "--password", "a-long-enough-password",
            ]
        )
        assert result.exit_code == 0
        assert "Created administrator" in result.output

        user = db.session.query(User).filter_by(username="cli-admin").one()
        assert user.is_admin
        assert user.has_api_key
        assert "ecoai_" in result.output  # key shown once

    def test_create_admin_promotes_an_existing_account(self, app, make_user):
        existing, _ = make_user("promote-via-cli", email="promote@example.com")
        runner = app.test_cli_runner()

        result = runner.invoke(
            args=[
                "create-admin",
                "--username", "promote-via-cli",
                "--email", "promote@example.com",
                "--password", "unused-because-it-exists",
            ]
        )
        assert result.exit_code == 0
        assert "Promoted" in result.output
        assert db.session.get(User, existing.id).is_admin is True

    def test_create_admin_rejects_a_weak_password(self, app):
        runner = app.test_cli_runner()
        result = runner.invoke(
            args=[
                "create-admin",
                "--username", "weak",
                "--email", "weak@example.com",
                "--password", "short",
            ]
        )
        assert result.exit_code == 1
        assert db.session.query(User).filter_by(username="weak").count() == 0

    def test_issue_api_key_rotates(self, app, make_user, client):
        target, old_secret = make_user("rotate-via-cli")
        runner = app.test_cli_runner()

        result = runner.invoke(args=["issue-api-key", "rotate-via-cli"])
        assert result.exit_code == 0

        new_secret = result.output.strip().splitlines()[-1]
        assert new_secret != old_secret
        assert client.get("/api/v1/me", headers={"X-API-Key": new_secret}).status_code == 200
        assert client.get("/api/v1/me", headers={"X-API-Key": old_secret}).status_code == 401

    def test_issue_api_key_for_unknown_user_fails(self, app):
        runner = app.test_cli_runner()
        result = runner.invoke(args=["issue-api-key", "nobody-here"])
        assert result.exit_code == 1
        assert "No account" in result.output

    def test_init_db_creates_tables(self, app):
        result = app.test_cli_runner().invoke(args=["init-db"])
        assert result.exit_code == 0
        assert "Tables created" in result.output
