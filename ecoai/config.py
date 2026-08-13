"""Environment driven configuration.

Every tunable and every secret is read from the environment, following the
twelve-factor convention. In development ``.env`` at the repository root is
loaded automatically; in production the platform supplies real environment
variables and no ``.env`` file needs to exist.

:class:`Config.validate` is called during application startup and raises
:class:`ConfigError` for anything that would be unsafe to run with, so a
misconfigured deployment fails loudly at boot rather than silently degrading.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"

load_dotenv(BASE_DIR / ".env")


class ConfigError(RuntimeError):
    """Raised when the environment is missing or contradicts something required."""


_TRUTHY = {"1", "true", "yes", "on"}
_FALSEY = {"0", "false", "no", "off"}


def env_str(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None else value.strip()


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSEY:
        return False
    raise ConfigError(
        f"{name}={raw!r} is not a boolean. Use one of: {', '.join(sorted(_TRUTHY | _FALSEY))}."
    )


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name}={raw!r} is not an integer.") from exc


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name}={raw!r} is not a number.") from exc


def normalize_database_url(url: str) -> str:
    """Return a URL SQLAlchemy 2.x can open.

    Heroku (and several other providers) inject ``postgres://``, a scheme
    SQLAlchemy dropped in 1.4. We rewrite it to the psycopg3 dialect that is
    actually installed, so the platform-provided value works untouched.

    Only the scheme is replaced, and only for PostgreSQL. Round-tripping
    through ``urlunsplit`` would corrupt anything else: ``sqlite:///x.db`` has
    an empty netloc, so reassembly drops two slashes and yields
    ``sqlite:/x.db``, which SQLAlchemy cannot open.
    """
    if not url:
        return url

    scheme = urlsplit(url).scheme
    if scheme in {"postgres", "postgresql"}:
        return f"postgresql+psycopg:{url.split(':', 1)[1]}"
    if scheme.startswith("sqlite"):
        return _absolutize_sqlite_url(url)
    return url


def _absolutize_sqlite_url(url: str) -> str:
    """Anchor a relative SQLite path to the repository root.

    A relative path in a SQLite URL is ambiguous: SQLAlchemy would resolve it
    against the process working directory, while Flask-SQLAlchemy rewrites it
    to sit under ``app.instance_path`` - so ``sqlite:///instance/ecoai.db``
    with an instance path of ``<repo>/instance`` ends up looking for
    ``<repo>/instance/instance/ecoai.db`` and fails to open.

    Resolving here means the configured path means the same thing however the
    process was launched: ``flask``, ``gunicorn``, pytest, or a cron job from
    some other directory.
    """
    prefix, _, path = url.partition(":///")
    if not path or path == ":memory:" or path.startswith("/"):
        # In-memory (``sqlite://`` or ``sqlite:///:memory:``) or already
        # absolute (``sqlite:////abs/path``, which leaves a leading slash).
        return url
    return f"{prefix}:///{(BASE_DIR / path).resolve()}"


def _default_sqlite_url() -> str:
    return f"sqlite:///{INSTANCE_DIR / 'ecoai.db'}"


@dataclass(frozen=True)
class MailConfig:
    """SMTP settings. ``enabled`` gates all outbound delivery."""

    enabled: bool
    host: str
    port: int
    use_tls: bool
    username: str
    password: str
    from_email: str
    from_name: str

    @classmethod
    def from_env(cls) -> MailConfig:
        return cls(
            enabled=env_bool("MAIL_ENABLED", False),
            host=env_str("SMTP_HOST", "smtp.gmail.com"),
            port=env_int("SMTP_PORT", 587),
            use_tls=env_bool("SMTP_USE_TLS", True),
            username=env_str("SMTP_USERNAME"),
            password=env_str("SMTP_PASSWORD"),
            from_email=env_str("MAIL_FROM_EMAIL", "noreply@example.com"),
            from_name=env_str("MAIL_FROM_NAME", "EcoAI Portal"),
        )


@dataclass(frozen=True)
class OAuthConfig:
    """Google OAuth client credentials. Both must be set for sign-in to appear."""

    google_client_id: str
    google_client_secret: str

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @classmethod
    def from_env(cls) -> OAuthConfig:
        return cls(
            google_client_id=env_str("GOOGLE_CLIENT_ID"),
            google_client_secret=env_str("GOOGLE_CLIENT_SECRET"),
        )


@dataclass(frozen=True)
class CarbonConfig:
    """Coefficients for the emissions estimate. See services/carbon.py."""

    pue: float
    joules_per_flop: float
    default_grid_intensity: float
    default_active_params: float

    @classmethod
    def from_env(cls) -> CarbonConfig:
        return cls(
            pue=env_float("CARBON_PUE", 1.12),
            joules_per_flop=env_float("CARBON_JOULES_PER_FLOP", 1.75e-12),
            default_grid_intensity=env_float("CARBON_DEFAULT_GRID_INTENSITY", 480.0),
            default_active_params=env_float("CARBON_DEFAULT_ACTIVE_PARAMS", 8e9),
        )


@dataclass
class Config:
    """Resolved application configuration."""

    env: str = field(default_factory=lambda: env_str("ECOAI_ENV", "development").lower())
    secret_key: str = field(default_factory=lambda: env_str("SECRET_KEY"))
    base_url: str = field(
        default_factory=lambda: env_str("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    )
    port: int = field(default_factory=lambda: env_int("PORT", 8000))

    database_url: str = field(
        default_factory=lambda: normalize_database_url(
            env_str("DATABASE_URL") or _default_sqlite_url()
        )
    )
    sqlalchemy_echo: bool = field(default_factory=lambda: env_bool("SQLALCHEMY_ECHO", False))

    remember_cookie_days: int = field(default_factory=lambda: env_int("REMEMBER_COOKIE_DAYS", 14))
    ratelimit_storage_uri: str = field(
        default_factory=lambda: env_str("RATELIMIT_STORAGE_URI", "memory://")
    )
    ratelimit_login: str = field(default_factory=lambda: env_str("RATELIMIT_LOGIN", "10 per minute"))
    ratelimit_signup: str = field(default_factory=lambda: env_str("RATELIMIT_SIGNUP", "5 per hour"))
    ratelimit_api: str = field(default_factory=lambda: env_str("RATELIMIT_API", "120 per minute"))
    ratelimit_email: str = field(default_factory=lambda: env_str("RATELIMIT_EMAIL", "3 per hour"))

    log_level: str = field(default_factory=lambda: env_str("LOG_LEVEL", "INFO").upper())
    log_format: str = field(default_factory=lambda: env_str("LOG_FORMAT", "console").lower())

    mail: MailConfig = field(default_factory=MailConfig.from_env)
    oauth: OAuthConfig = field(default_factory=OAuthConfig.from_env)
    carbon: CarbonConfig = field(default_factory=CarbonConfig.from_env)

    _session_cookie_secure_override: bool | None = field(
        default_factory=lambda: (
            None if os.environ.get("SESSION_COOKIE_SECURE") is None
            else env_bool("SESSION_COOKIE_SECURE", True)
        )
    )

    # -- Derived -----------------------------------------------------------

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_testing(self) -> bool:
        return self.env == "testing"

    @property
    def debug(self) -> bool:
        return self.env == "development"

    @property
    def session_cookie_secure(self) -> bool:
        """HTTPS-only cookies. On by default in production, off elsewhere.

        Forcing this on in local development would silently break login, since
        the dev server speaks plain HTTP and the browser would drop the cookie.
        """
        if self._session_cookie_secure_override is not None:
            return self._session_cookie_secure_override
        return self.is_production

    # -- Validation --------------------------------------------------------

    def validate(self) -> None:
        """Fail fast on configuration that is missing, unsafe, or contradictory."""
        valid_envs = {"development", "testing", "production"}
        if self.env not in valid_envs:
            raise ConfigError(
                f"ECOAI_ENV={self.env!r} is invalid. Expected one of: {', '.join(sorted(valid_envs))}."
            )

        if self.is_production:
            if not self.secret_key:
                raise ConfigError(
                    "SECRET_KEY must be set in production. Without it every process would "
                    "generate its own key, so sessions would break across workers and be "
                    "dropped on every restart. Generate one with:\n"
                    '    python -c "import secrets; print(secrets.token_urlsafe(64))"'
                )
            if len(self.secret_key) < 32:
                raise ConfigError(
                    f"SECRET_KEY is only {len(self.secret_key)} characters. Use at least 32."
                )
            if self.database_url.startswith("sqlite:"):
                raise ConfigError(
                    "SQLite is not supported in production. Container filesystems are "
                    "ephemeral, so every restart would discard all accounts and receipts. "
                    "Set DATABASE_URL to a PostgreSQL instance."
                )
            if not self.base_url.startswith("https://"):
                raise ConfigError(
                    f"APP_BASE_URL={self.base_url!r} must use https:// in production."
                )

        if self.mail.enabled:
            missing = [
                name
                for name, value in (
                    ("SMTP_HOST", self.mail.host),
                    ("SMTP_USERNAME", self.mail.username),
                    ("SMTP_PASSWORD", self.mail.password),
                    ("MAIL_FROM_EMAIL", self.mail.from_email),
                )
                if not value
            ]
            if missing:
                raise ConfigError(
                    f"MAIL_ENABLED is true but {', '.join(missing)} not set. "
                    "Either provide the SMTP credentials or set MAIL_ENABLED=false."
                )

        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError(f"LOG_LEVEL={self.log_level!r} is not a valid level.")

        if self.carbon.pue < 1.0:
            raise ConfigError(
                f"CARBON_PUE={self.carbon.pue} is below 1.0, which would mean a datacenter "
                "consuming less power than the chips inside it."
            )

    # -- Flask mapping -----------------------------------------------------

    def resolve_secret_key(self) -> str:
        """Return the signing key, generating an ephemeral one outside production.

        :meth:`validate` already guarantees a real key exists in production, so
        the generated fallback only ever applies to local runs and tests where
        losing sessions on restart is harmless.
        """
        return self.secret_key or secrets.token_urlsafe(64)

    def as_flask_mapping(self) -> dict[str, object]:
        """Translate into the ``app.config`` keys Flask and its extensions read."""
        return {
            "ENV": self.env,
            "DEBUG": self.debug,
            "TESTING": self.is_testing,
            "SECRET_KEY": self.resolve_secret_key(),
            "PORT": self.port,
            "DEV_SERVER_HOST": "127.0.0.1",
            "APP_BASE_URL": self.base_url,
            "SQLALCHEMY_DATABASE_URI": self.database_url,
            "SQLALCHEMY_ECHO": self.sqlalchemy_echo,
            "SQLALCHEMY_ENGINE_OPTIONS": self._engine_options(),
            "SESSION_COOKIE_SECURE": self.session_cookie_secure,
            "SESSION_COOKIE_HTTPONLY": True,
            "SESSION_COOKIE_SAMESITE": "Lax",
            "REMEMBER_COOKIE_SECURE": self.session_cookie_secure,
            "REMEMBER_COOKIE_HTTPONLY": True,
            "REMEMBER_COOKIE_SAMESITE": "Lax",
            "REMEMBER_COOKIE_DURATION": self.remember_cookie_days * 86400,
            # CSRF tokens live as long as the session rather than expiring after
            # an hour, which otherwise breaks long-lived dashboard tabs.
            "WTF_CSRF_TIME_LIMIT": None,
            "WTF_CSRF_ENABLED": not self.is_testing,
            "RATELIMIT_STORAGE_URI": self.ratelimit_storage_uri,
            "RATELIMIT_HEADERS_ENABLED": True,
            "RATELIMIT_ENABLED": not self.is_testing,
            "MAX_CONTENT_LENGTH": 2 * 1024 * 1024,
            "ECOAI": self,
        }

    def _engine_options(self) -> dict[str, object]:
        if self.database_url.startswith("sqlite"):
            # SQLite needs no pooling knobs, and pool_size is rejected outright
            # by its default NullPool/StaticPool.
            return {}
        return {
            "pool_pre_ping": True,
            "pool_recycle": 280,
            "pool_size": 5,
            "max_overflow": 5,
        }


def load_config() -> Config:
    """Build and validate configuration from the current environment."""
    config = Config()
    config.validate()
    return config
