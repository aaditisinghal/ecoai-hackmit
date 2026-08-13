"""User account model."""

from __future__ import annotations

import uuid
from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ecoai.models.base import Base, TimestampMixin


class User(UserMixin, TimestampMixin, Base):
    """A portal account.

    Accounts arrive either through email/password signup or through Google
    OAuth. OAuth accounts have no ``password_hash`` and cannot log in through
    the password form; password accounts have no ``oauth_subject``.

    API keys are stored only as a SHA-256 digest. ``api_key_prefix`` keeps the
    leading characters so the UI can identify a key without being able to
    reproduce it - a database leak therefore yields no usable credentials.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("oauth_provider", "oauth_subject", name="uq_users_oauth_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Stable external identifier. Exposed in APIs so the integer primary key,
    # which leaks signup order and total user count, never appears publicly.
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()), nullable=False
    )

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)

    # Null for OAuth-only accounts.
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)

    api_key_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, default=None
    )
    api_key_prefix: Mapped[str | None] = mapped_column(String(24), default=None)
    api_key_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    oauth_provider: Mapped[str | None] = mapped_column(String(32), default=None)
    oauth_subject: Mapped[str | None] = mapped_column(String(255), default=None)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Overrides UserMixin.is_active; Flask-Login refuses to log in a user whose
    # is_active is False, which is how deactivation is enforced.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    receipts = relationship(
        "Receipt", back_populates="user", cascade="all, delete-orphan", lazy="dynamic"
    )

    def get_id(self) -> str:
        """Session identifier for Flask-Login."""
        return str(self.id)

    @property
    def has_password(self) -> bool:
        return bool(self.password_hash)

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key_hash)

    @property
    def display_api_key(self) -> str:
        """Masked key for display. The real key is unrecoverable by design."""
        if not self.api_key_prefix:
            return "not issued"
        return f"{self.api_key_prefix}{'•' * 8}"

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
