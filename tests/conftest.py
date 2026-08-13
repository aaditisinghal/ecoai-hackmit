"""Shared pytest fixtures.

Each test gets a fresh in-memory database and its own application instance,
which is what the app factory exists to make possible.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pytest

os.environ.setdefault("ECOAI_ENV", "testing")

from ecoai import create_app
from ecoai.config import Config
from ecoai.extensions import db
from ecoai.models import Receipt, User, utcnow
from ecoai.services.credentials import generate_api_key, hash_password

TEST_PASSWORD = "correct-horse-battery"


@pytest.fixture
def config() -> Config:
    cfg = Config()
    cfg.env = "testing"
    cfg.secret_key = "test-secret-key-long-enough-to-satisfy-validation-rules"
    cfg.database_url = "sqlite://"  # in-memory
    cfg.base_url = "http://localhost:8000"
    cfg.log_level = "WARNING"
    cfg.validate()
    return cfg


@pytest.fixture
def app(config: Config):
    application = create_app(config)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(app):
    """Factory for accounts. Returns ``(user, api_key_secret)``."""

    def _make(
        username: str = "tester",
        email: str | None = None,
        *,
        password: str | None = TEST_PASSWORD,
        is_admin: bool = False,
        is_active: bool = True,
        with_api_key: bool = True,
        password_hash: str | None = None,
    ) -> tuple[User, str | None]:
        user = User(
            username=username,
            email=email or f"{username}@example.com",
            password_hash=password_hash
            if password_hash is not None
            else (hash_password(password) if password else None),
            is_admin=is_admin,
            is_active=is_active,
        )

        secret = None
        if with_api_key:
            issued = generate_api_key()
            secret = issued.secret
            user.api_key_hash = issued.hashed
            user.api_key_prefix = issued.prefix
            user.api_key_created_at = utcnow()

        db.session.add(user)
        db.session.commit()
        return user, secret

    return _make


@pytest.fixture
def user(make_user):
    created, secret = make_user()
    created.api_key_secret = secret  # convenience for tests
    return created


@pytest.fixture
def admin(make_user):
    created, secret = make_user(username="root-admin", is_admin=True)
    created.api_key_secret = secret
    return created


@pytest.fixture
def auth_client(client, user):
    """A client with an established session for ``user``."""
    response = client.post(
        "/login",
        data={"identifier": user.username, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 302, "login fixture failed to establish a session"
    return client


@pytest.fixture
def admin_client(client, admin):
    response = client.post(
        "/login",
        data={"identifier": admin.username, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 302
    return client


@pytest.fixture
def make_receipts(app):
    """Factory that writes receipts for a user, dated N days back."""

    def _make(user: User, count: int = 5, *, days_back: int = 0, model: str = "gpt-4o-mini"):
        created = []
        for index in range(count):
            receipt = Receipt(
                receipt_id=f"rcpt-{user.id}-{days_back}-{index}",
                user_id=user.id,
                tokens_before=100 + index,
                tokens_after=70 + index,
                kwh_before=0.001,
                kwh_after=0.0007,
                co2_g_before=0.35,
                co2_g_after=0.245,
                retention_score=0.95,
                model=model,
                region="us-east-1",
                strategy="balanced",
                optimizations_applied=[],
                created_at=utcnow() - timedelta(days=days_back),
            )
            db.session.add(receipt)
            created.append(receipt)
        db.session.commit()
        return created

    return _make
