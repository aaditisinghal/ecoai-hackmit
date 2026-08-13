"""Google sign-in.

Replaces the previous ``/auth/google`` and ``/auth/apple`` routes, which
performed no authentication at all: they generated a random username, created
an account for it, and started a session. Anyone who opened the URL was signed
in as a brand new user.

This blueprint is registered only when ``GOOGLE_CLIENT_ID`` and
``GOOGLE_CLIENT_SECRET`` are both present, so the app runs unchanged without
OAuth configured and the sign-in button simply does not appear.

Apple Sign-In was dropped rather than stubbed. It needs a paid developer
account and ES256-signed client secrets that rotate every six months; a
placeholder implementation would be another route that looks like
authentication without being any.
"""

from __future__ import annotations

import logging
import secrets

from authlib.integrations.base_client import OAuthError
from flask import Blueprint, current_app, flash, redirect, session, url_for
from flask_login import current_user, login_user
from sqlalchemy import select

from ecoai.extensions import db, oauth
from ecoai.models import User, utcnow
from ecoai.services.credentials import generate_api_key

logger = logging.getLogger(__name__)

bp = Blueprint("oauth", __name__, url_prefix="/auth/google")

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


def register_google_client(app) -> None:
    """Configure the Authlib client. Called from the app factory."""
    oauth.register(
        name="google",
        client_id=app.config["ECOAI"].oauth.google_client_id,
        client_secret=app.config["ECOAI"].oauth.google_client_secret,
        server_metadata_url=GOOGLE_DISCOVERY_URL,
        client_kwargs={"scope": "openid email profile"},
    )


@bp.route("/")
def start():
    """Redirect to Google's consent screen."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    redirect_uri = url_for("oauth.callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@bp.route("/callback")
def callback():
    """Handle the redirect back from Google."""
    try:
        token = oauth.google.authorize_access_token()
    except OAuthError as exc:
        logger.warning("Google OAuth failed", extra={"error": str(exc)})
        flash("Google sign-in was cancelled or failed.", "error")
        return redirect(url_for("auth.login"))

    claims = token.get("userinfo") or {}
    subject = claims.get("sub")
    email = (claims.get("email") or "").strip().lower()

    if not subject or not email:
        flash("Google did not return an email address for that account.", "error")
        return redirect(url_for("auth.login"))

    if not claims.get("email_verified", False):
        # An unverified address could belong to someone else, which would let
        # an attacker claim an existing account by matching on email.
        flash("Your Google email address is not verified.", "error")
        return redirect(url_for("auth.login"))

    user = _find_or_create(subject=subject, email=email, name=claims.get("name"))

    if not user.is_active:
        flash("That account has been deactivated. Contact an administrator.", "error")
        return redirect(url_for("auth.login"))

    login_user(user)
    user.last_login_at = utcnow()
    db.session.commit()

    logger.info("Google sign-in", extra={"user_id": user.id})
    return redirect(url_for("dashboard.index"))


def _find_or_create(*, subject: str, email: str, name: str | None) -> User:
    """Resolve the Google identity to an account, creating one if needed."""
    user = db.session.execute(
        select(User).where(User.oauth_provider == "google", User.oauth_subject == subject)
    ).scalar_one_or_none()
    if user is not None:
        return user

    # Link to an existing password account with the same verified address
    # rather than creating a duplicate.
    user = db.session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None:
        user.oauth_provider = "google"
        user.oauth_subject = subject
        db.session.commit()
        logger.info("Linked Google identity to existing account", extra={"user_id": user.id})
        return user

    user = User(
        username=_unique_username(name or email.split("@")[0]),
        email=email,
        oauth_provider="google",
        oauth_subject=subject,
    )
    issued = generate_api_key()
    user.api_key_hash = issued.hashed
    user.api_key_prefix = issued.prefix
    user.api_key_created_at = utcnow()

    db.session.add(user)
    db.session.commit()

    # The key is unrecoverable, so send the new user somewhere they can mint
    # one they actually see.
    session["_oauth_new_account"] = True
    logger.info("Created account from Google sign-in", extra={"user_id": user.id})
    return user


def _unique_username(preferred: str) -> str:
    base = "".join(ch for ch in preferred.lower().replace(" ", "_") if ch.isalnum() or ch in "_.-")
    base = (base or "user")[:48]

    candidate = base
    while db.session.execute(select(User.id).where(User.username == candidate)).scalar_one_or_none():
        candidate = f"{base}_{secrets.token_hex(3)}"
    return candidate


def is_enabled() -> bool:
    return current_app.config["ECOAI"].oauth.google_enabled
