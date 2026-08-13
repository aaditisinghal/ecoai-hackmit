"""EcoAI Portal application factory."""

from __future__ import annotations

import logging
from datetime import UTC
from pathlib import Path

from flask import Flask

from ecoai.config import INSTANCE_DIR, Config, load_config
from ecoai.errors import register_error_handlers
from ecoai.extensions import csrf, db, limiter, login_manager, migrate, oauth
from ecoai.logging_config import configure_logging

__version__ = "2.0.0"

logger = logging.getLogger(__name__)


def create_app(config: Config | None = None) -> Flask:
    """Build a configured application.

    A factory rather than a module-level ``app`` object, so tests can build
    isolated instances and nothing is constructed as a side effect of import.
    """
    config = config or load_config()
    configure_logging(config.log_level, config.log_format)

    app = Flask(__name__, instance_path=str(INSTANCE_DIR))
    app.config.update(config.as_flask_mapping())

    _ensure_instance_dir(config)
    _init_extensions(app, config)
    _register_blueprints(app, config)
    _register_shared_services(app, config)
    _register_template_globals(app, config)
    _register_security_headers(app)
    register_error_handlers(app)

    from ecoai import cli

    cli.register(app)

    logger.info(
        "Application ready",
        extra={
            "env": config.env,
            "database": _redact(config.database_url),
            "google_oauth": config.oauth.google_enabled,
            "mail": config.mail.enabled,
        },
    )
    return app


def _ensure_instance_dir(config: Config) -> None:
    """SQLite cannot create its parent directory, so do it here."""
    if config.database_url.startswith("sqlite"):
        Path(INSTANCE_DIR).mkdir(parents=True, exist_ok=True)


def _init_extensions(app: Flask, config: Config) -> None:
    db.init_app(app)
    migrate.init_app(app, db, directory=str(Path(app.root_path).parent / "migrations"))
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Sign in to view that page."
    login_manager.login_message_category = "info"
    # "strong" invalidates a session whose client fingerprint changes, which
    # limits the damage from a stolen cookie.
    login_manager.session_protection = "strong"

    @login_manager.user_loader
    def load_user(user_id: str):
        from ecoai.models import User

        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    if config.oauth.google_enabled:
        oauth.init_app(app)


def _register_blueprints(app: Flask, config: Config) -> None:
    from ecoai.blueprints import admin, api, auth, dashboard, public, studio

    app.register_blueprint(public.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(studio.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(api.bp)

    # Token-authenticated; session-authenticated calls validate CSRF explicitly
    # inside the decorator. See ecoai.security.api_key_or_session_required.
    csrf.exempt(api.bp)

    if config.oauth.google_enabled:
        from ecoai.blueprints import oauth as oauth_bp

        oauth_bp.register_google_client(app)
        app.register_blueprint(oauth_bp.bp)


def _register_shared_services(app: Flask, config: Config) -> None:
    """Attach long-lived service objects to the app rather than to globals."""
    from ecoai.services.carbon import CarbonCalculator
    from ecoai.services.mailer import Mailer

    app.extensions["ecoai_carbon"] = CarbonCalculator.from_config(config.carbon)
    app.extensions["ecoai_mailer"] = Mailer(config.mail)


def _register_template_globals(app: Flask, config: Config) -> None:
    from datetime import datetime

    @app.context_processor
    def inject_globals():
        return {
            "app_version": __version__,
            "google_oauth_enabled": config.oauth.google_enabled,
            "mail_enabled": config.mail.enabled,
            "current_year": datetime.now(UTC).year,
        }

    @app.template_filter("gram")
    def format_grams(value: float | None) -> str:
        """Render a CO2 mass at a readable scale."""
        if value is None:
            return "—"
        if abs(value) >= 1000:
            return f"{value / 1000:,.2f} kg"
        if abs(value) >= 1:
            return f"{value:,.2f} g"
        return f"{value * 1000:,.2f} mg"

    @app.template_filter("usd")
    def format_usd(value: float | None) -> str:
        if value is None:
            return "—"
        if 0 < abs(value) < 0.01:
            return f"${value:.4f}"
        return f"${value:,.2f}"

    @app.template_filter("pct")
    def format_pct(value: float | None) -> str:
        return "—" if value is None else f"{value * 100:.1f}%"


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def set_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        # Self-hosted assets only; no CDN, so this can stay tight. 'unsafe-inline'
        # covers the small amount of chart bootstrap data embedded per page.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


def _redact(database_url: str) -> str:
    """Strip credentials before a connection string reaches the logs."""
    if "@" not in database_url:
        return database_url
    scheme, _, rest = database_url.partition("://")
    return f"{scheme}://***@{rest.rpartition('@')[2]}"
