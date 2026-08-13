"""Authentication and authorization decorators."""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any

from flask import abort, current_app, g, jsonify, request
from flask_login import current_user
from sqlalchemy import select

from ecoai.extensions import db
from ecoai.models import User
from ecoai.services.credentials import hash_api_key, looks_like_api_key

logger = logging.getLogger(__name__)


def _extract_api_key() -> str | None:
    """Read the key from ``X-API-Key`` or an ``Authorization: Bearer`` header."""
    header = request.headers.get("X-API-Key")
    if header:
        return header.strip()

    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return None


def resolve_api_user(secret: str) -> User | None:
    """Look up the account owning an API key, or None."""
    if not looks_like_api_key(secret):
        return None
    return db.session.execute(
        select(User).where(User.api_key_hash == hash_api_key(secret), User.is_active.is_(True))
    ).scalar_one_or_none()


def api_key_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """Require a valid API key, exposing the account as ``g.api_user``.

    Both failure modes answer 401. The old implementation returned 401 for a
    missing key and 403 for an invalid one, which let an unauthenticated caller
    distinguish real keys from fabricated ones.
    """

    @functools.wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        secret = _extract_api_key()
        if not secret:
            return (
                jsonify(
                    {
                        "error": "authentication_required",
                        "message": "Provide an API key in the X-API-Key header.",
                    }
                ),
                401,
            )

        user = resolve_api_user(secret)
        if user is None:
            logger.warning(
                "Rejected API request with invalid key",
                extra={"path": request.path, "remote_addr": request.remote_addr},
            )
            return (
                jsonify(
                    {
                        "error": "authentication_required",
                        "message": "That API key is not valid.",
                    }
                ),
                401,
            )

        g.api_user = user
        return view(*args, **kwargs)

    return wrapper


def api_key_or_session_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """Accept either an API key or a signed-in browser session.

    Used by endpoints the Prompt Studio calls from the page as well as the SDK.

    The two paths have different CSRF properties, so they are handled
    differently:

    * **API key.** A cross-origin page cannot attach an ``X-API-Key`` header
      without clearing a CORS preflight, so requiring the header is itself
      sufficient CSRF protection. No token needed.
    * **Session cookie.** Cookies ride along on cross-site requests, so the
      caller must present a valid CSRF token. The API blueprint is exempt from
      the global CSRFProtect hook, so it is validated explicitly here rather
      than being silently skipped.
    """

    @functools.wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        secret = _extract_api_key()
        if secret:
            user = resolve_api_user(secret)
            if user is None:
                return (
                    jsonify(
                        {"error": "authentication_required", "message": "That API key is not valid."}
                    ),
                    401,
                )
            g.api_user = user
            return view(*args, **kwargs)

        if current_user.is_authenticated:
            error = _validate_session_csrf()
            if error is not None:
                return error
            g.api_user = current_user
            return view(*args, **kwargs)

        return (
            jsonify(
                {
                    "error": "authentication_required",
                    "message": "Provide an API key in the X-API-Key header, or sign in.",
                }
            ),
            401,
        )

    return wrapper


def _validate_session_csrf():
    """Enforce a CSRF token on cookie-authenticated state-changing requests."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return None
    if not current_app.config.get("WTF_CSRF_ENABLED", True):
        return None

    from flask_wtf.csrf import CSRFError, validate_csrf
    from wtforms.validators import ValidationError

    token = request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
    if not token and request.is_json:
        token = (request.get_json(silent=True) or {}).get("csrf_token")

    try:
        # validate_csrf raises wtforms' ValidationError, not CSRFError - only
        # CSRFProtect's own hook translates between the two, and this path
        # bypasses it. Catching CSRFError alone turned a missing token into a
        # 500 instead of a 400.
        validate_csrf(token)
    except (ValidationError, CSRFError) as exc:
        logger.warning(
            "Rejected session-authenticated API request with bad CSRF token",
            extra={"path": request.path, "reason": str(exc)},
        )
        return (
            jsonify(
                {
                    "error": "csrf_failed",
                    "message": "Missing or invalid CSRF token. Send it in the X-CSRFToken header.",
                }
            ),
            400,
        )
    return None


def admin_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """Require an authenticated session belonging to an administrator."""

    @functools.wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        if not current_user.is_authenticated:
            return current_app.login_manager.unauthorized()
        if not current_user.is_admin:
            logger.warning(
                "Non-admin attempted to reach an admin route",
                extra={"user_id": current_user.id, "path": request.path},
            )
            abort(403)
        return view(*args, **kwargs)

    return wrapper
