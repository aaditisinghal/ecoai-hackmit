"""Session authentication: signup, login, profile, API key management."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_, select

from ecoai.extensions import db, limiter
from ecoai.forms import (
    ChangePasswordForm,
    LoginForm,
    RotateApiKeyForm,
    SignupForm,
    normalize_email,
    normalize_username,
)
from ecoai.models import User, utcnow
from ecoai.services.credentials import (
    generate_api_key,
    hash_password,
    needs_rehash,
    verify_password,
)

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__)

#: Session key holding a freshly issued API key for exactly one redirect.
NEW_KEY_SESSION_FIELD = "_new_api_key"


def _is_safe_redirect(target: str | None) -> bool:
    """Only allow same-origin relative redirects.

    Without this check ``/login?next=https://evil.example`` turns the login
    form into an open redirect, which is a standard phishing primitive.
    """
    if not target:
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc and target.startswith("/")


def _issue_api_key(user: User) -> str:
    """Mint and store a key, returning the secret for one-time display."""
    issued = generate_api_key()
    user.api_key_hash = issued.hashed
    user.api_key_prefix = issued.prefix
    user.api_key_created_at = utcnow()
    return issued.secret


@bp.route("/signup", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["ECOAI"].ratelimit_signup, methods=["POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = SignupForm()
    if form.validate_on_submit():
        username = normalize_username(form.username.data)
        email = normalize_email(form.email.data)

        existing = db.session.execute(
            select(User).where(
                or_(func.lower(User.username) == username.lower(), User.email == email)
            )
        ).scalar_one_or_none()

        if existing is not None:
            # Deliberately vague: naming which field collided would let anyone
            # enumerate registered usernames and email addresses.
            flash("That username or email is already registered.", "error")
            return render_template("auth/signup.html", form=form), 400

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(form.password.data),
        )
        db.session.add(user)
        db.session.flush()

        secret = _issue_api_key(user)
        db.session.commit()

        logger.info("Account created", extra={"user_id": user.id})

        login_user(user)
        user.last_login_at = utcnow()
        db.session.commit()

        session[NEW_KEY_SESSION_FIELD] = secret
        flash("Welcome to EcoAI. Copy your API key now — it is shown only once.", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/signup.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["ECOAI"].ratelimit_login, methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    if form.validate_on_submit():
        identifier = (form.identifier.data or "").strip()

        user = db.session.execute(
            select(User).where(
                or_(
                    func.lower(User.username) == identifier.lower(),
                    User.email == identifier.lower(),
                )
            )
        ).scalar_one_or_none()

        if user is None or not verify_password(user.password_hash, form.password.data):
            logger.info(
                "Failed login attempt",
                extra={"identifier": identifier, "remote_addr": request.remote_addr},
            )
            flash("Incorrect username or password.", "error")
            return render_template("auth/login.html", form=form), 401

        if not user.is_active:
            flash("That account has been deactivated. Contact an administrator.", "error")
            return render_template("auth/login.html", form=form), 403

        # Upgrade the inherited unsalted SHA-256 digest now that we have the
        # cleartext password in hand and know it is correct.
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(form.password.data)
            logger.info("Upgraded legacy password hash", extra={"user_id": user.id})

        login_user(user, remember=bool(form.remember.data))
        user.last_login_at = utcnow()
        db.session.commit()

        next_url = request.args.get("next")
        return redirect(next_url if _is_safe_redirect(next_url) else url_for("dashboard.index"))

    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("public.home"))


@bp.route("/profile")
@login_required
def profile():
    # Present only on the redirect immediately after issuing a key.
    new_api_key = session.pop(NEW_KEY_SESSION_FIELD, None)

    response = render_template(
        "auth/profile.html",
        new_api_key=new_api_key,
        rotate_form=RotateApiKeyForm(),
        password_form=ChangePasswordForm(),
    )
    if new_api_key:
        return response, 200, {"Cache-Control": "no-store"}
    return response


@bp.route("/profile/api-key/rotate", methods=["POST"])
@login_required
def rotate_api_key():
    form = RotateApiKeyForm()
    if not form.validate_on_submit():
        flash("That request could not be verified. Please try again.", "error")
        return redirect(url_for("auth.profile"))

    secret = _issue_api_key(current_user)
    db.session.commit()
    logger.info("API key rotated", extra={"user_id": current_user.id})

    session[NEW_KEY_SESSION_FIELD] = secret
    flash("New API key generated. The previous key stopped working immediately.", "success")
    return redirect(url_for("auth.profile"))


@bp.route("/profile/password", methods=["POST"])
@login_required
def change_password():
    form = ChangePasswordForm()

    if not form.validate_on_submit():
        for errors in form.errors.values():
            for error in errors:
                flash(error, "error")
        return redirect(url_for("auth.profile"))

    if not verify_password(current_user.password_hash, form.current_password.data):
        flash("Your current password is incorrect.", "error")
        return redirect(url_for("auth.profile"))

    current_user.password_hash = hash_password(form.new_password.data)
    db.session.commit()
    logger.info("Password changed", extra={"user_id": current_user.id})

    flash("Password updated.", "success")
    return redirect(url_for("auth.profile"))
