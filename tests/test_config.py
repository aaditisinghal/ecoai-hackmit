"""Configuration loading and validation."""

from __future__ import annotations

import pytest

from ecoai.config import Config, ConfigError, env_bool, normalize_database_url


class TestDatabaseUrlNormalization:
    def test_heroku_postgres_scheme_is_rewritten(self):
        """Heroku injects postgres://, which SQLAlchemy 2.x cannot open."""
        assert normalize_database_url("postgres://u:p@host:5432/db") == (
            "postgresql+psycopg://u:p@host:5432/db"
        )

    def test_postgresql_scheme_gets_the_installed_driver(self):
        assert normalize_database_url("postgresql://u:p@host/db").startswith(
            "postgresql+psycopg://"
        )

    def test_relative_sqlite_path_is_anchored_to_the_repo_root(self):
        """Otherwise the path means different things to Flask-SQLAlchemy,
        SQLAlchemy, and whatever directory the process was started from."""
        from ecoai.config import BASE_DIR

        resolved = normalize_database_url("sqlite:///instance/ecoai.db")
        assert resolved == f"sqlite:///{BASE_DIR / 'instance' / 'ecoai.db'}"
        assert resolved.startswith("sqlite:////")

    def test_absolute_sqlite_path_is_untouched(self):
        assert normalize_database_url("sqlite:////var/data/x.db") == "sqlite:////var/data/x.db"

    def test_in_memory_sqlite_is_untouched(self):
        assert normalize_database_url("sqlite://") == "sqlite://"
        assert normalize_database_url("sqlite:///:memory:") == "sqlite:///:memory:"

    def test_query_string_survives(self):
        assert "sslmode=require" in normalize_database_url(
            "postgres://u:p@host/db?sslmode=require"
        )

    def test_empty_is_untouched(self):
        assert normalize_database_url("") == ""


class TestBooleanParsing:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_truthy(self, value, monkeypatch):
        monkeypatch.setenv("SOME_FLAG", value)
        assert env_bool("SOME_FLAG", False) is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off"])
    def test_falsey(self, value, monkeypatch):
        monkeypatch.setenv("SOME_FLAG", value)
        assert env_bool("SOME_FLAG", True) is False

    def test_unset_uses_default(self, monkeypatch):
        monkeypatch.delenv("SOME_FLAG", raising=False)
        assert env_bool("SOME_FLAG", True) is True

    def test_garbage_is_an_error_not_a_silent_false(self, monkeypatch):
        monkeypatch.setenv("SOME_FLAG", "maybe")
        with pytest.raises(ConfigError, match="not a boolean"):
            env_bool("SOME_FLAG", False)


class TestProductionValidation:
    def _production(self, **overrides) -> Config:
        config = Config()
        config.env = "production"
        config.secret_key = "k" * 64
        config.database_url = "postgresql+psycopg://u:p@host/db"
        config.base_url = "https://portal.example.com"
        for key, value in overrides.items():
            setattr(config, key, value)
        return config

    def test_valid_production_config_passes(self):
        self._production().validate()

    def test_missing_secret_key_is_fatal(self):
        with pytest.raises(ConfigError, match="SECRET_KEY must be set"):
            self._production(secret_key="").validate()

    def test_short_secret_key_is_fatal(self):
        with pytest.raises(ConfigError, match="at least 32"):
            self._production(secret_key="tooshort").validate()

    def test_sqlite_in_production_is_fatal(self):
        """The original deployment lost every signup on each dyno restart."""
        with pytest.raises(ConfigError, match="ephemeral"):
            self._production(database_url="sqlite:///instance/ecoai.db").validate()

    def test_plain_http_base_url_is_fatal(self):
        with pytest.raises(ConfigError, match="https"):
            self._production(base_url="http://portal.example.com").validate()

    def test_unknown_environment_is_fatal(self):
        config = Config()
        config.env = "staging"
        with pytest.raises(ConfigError, match="ECOAI_ENV"):
            config.validate()

    def test_pue_below_one_is_fatal(self):
        config = self._production()
        object.__setattr__(config.carbon, "pue", 0.5)
        with pytest.raises(ConfigError, match="below 1.0"):
            config.validate()


class TestMailValidation:
    def test_enabled_mail_without_credentials_is_fatal(self):
        config = Config()
        config.env = "development"
        object.__setattr__(config.mail, "enabled", True)
        object.__setattr__(config.mail, "username", "")
        object.__setattr__(config.mail, "password", "")
        with pytest.raises(ConfigError, match="SMTP_USERNAME"):
            config.validate()

    def test_disabled_mail_needs_nothing(self):
        config = Config()
        config.env = "development"
        object.__setattr__(config.mail, "enabled", False)
        config.validate()


class TestCookieSecurity:
    def test_secure_cookies_default_on_in_production(self):
        config = Config()
        config.env = "production"
        config._session_cookie_secure_override = None
        assert config.session_cookie_secure is True

    def test_secure_cookies_default_off_in_development(self):
        """Forcing Secure on plain HTTP would silently break local login."""
        config = Config()
        config.env = "development"
        config._session_cookie_secure_override = None
        assert config.session_cookie_secure is False

    def test_explicit_override_wins(self):
        config = Config()
        config.env = "development"
        config._session_cookie_secure_override = True
        assert config.session_cookie_secure is True


class TestSecretKeyFallback:
    def test_generated_when_absent_outside_production(self):
        config = Config()
        config.env = "development"
        config.secret_key = ""
        assert len(config.resolve_secret_key()) >= 32
        assert config.resolve_secret_key() != config.resolve_secret_key()

    def test_configured_key_is_stable(self):
        config = Config()
        config.secret_key = "k" * 64
        assert config.resolve_secret_key() == config.resolve_secret_key()


class TestFlaskMapping:
    def test_maps_the_keys_extensions_read(self):
        config = Config()
        config.env = "development"
        mapping = config.as_flask_mapping()

        assert mapping["SESSION_COOKIE_HTTPONLY"] is True
        assert mapping["SESSION_COOKIE_SAMESITE"] == "Lax"
        assert mapping["SQLALCHEMY_DATABASE_URI"] == config.database_url
        assert mapping["ECOAI"] is config

    def test_sqlite_gets_no_pool_options(self):
        """pool_size is rejected outright by SQLite's default pool class."""
        config = Config()
        config.database_url = "sqlite:///x.db"
        assert config.as_flask_mapping()["SQLALCHEMY_ENGINE_OPTIONS"] == {}

    def test_postgres_gets_pool_options(self):
        config = Config()
        config.database_url = "postgresql+psycopg://u:p@h/d"
        options = config.as_flask_mapping()["SQLALCHEMY_ENGINE_OPTIONS"]
        assert options["pool_pre_ping"] is True
        assert options["pool_size"] == 5
