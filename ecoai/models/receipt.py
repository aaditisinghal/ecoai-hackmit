"""Optimization receipt model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ecoai.models.base import Base, utcnow


class Receipt(Base):
    """One recorded optimization: what a prompt cost before and after.

    ``retention_score`` replaces the old ``quality_score``. The previous
    implementation hardcoded that field to 0.95 and called it quality; this one
    measures how much of the prompt's content survived optimization, which is
    what the number has always actually been able to describe. See
    :mod:`ecoai.services.optimizer`.
    """

    __tablename__ = "receipts"
    __table_args__ = (
        Index("ix_receipts_user_created", "user_id", "created_at"),
        Index("ix_receipts_user_model", "user_id", "model"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Client-supplied idempotency key. Re-ingesting the same receipt_id updates
    # the existing row rather than creating a duplicate.
    receipt_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    tokens_before: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_after: Mapped[int] = mapped_column(Integer, nullable=False)

    kwh_before: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    kwh_after: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    co2_g_before: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    co2_g_after: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    retention_score: Mapped[float | None] = mapped_column(Float, default=None)

    model: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    region: Mapped[str | None] = mapped_column(String(64), default=None)
    strategy: Mapped[str | None] = mapped_column(String(32), default=None)

    optimizations_applied: Mapped[list | None] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    user = relationship("User", back_populates="receipts")

    # -- Derived ----------------------------------------------------------

    @property
    def tokens_saved(self) -> int:
        return self.tokens_before - self.tokens_after

    @property
    def co2_g_saved(self) -> float:
        return self.co2_g_before - self.co2_g_after

    @property
    def kwh_saved(self) -> float:
        return self.kwh_before - self.kwh_after

    @property
    def reduction_ratio(self) -> float:
        if not self.tokens_before:
            return 0.0
        return self.tokens_saved / self.tokens_before

    def to_dict(self) -> dict:
        """Public representation. Internal ids are deliberately excluded."""
        return {
            "receipt_id": self.receipt_id,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "tokens_saved": self.tokens_saved,
            "kwh_before": self.kwh_before,
            "kwh_after": self.kwh_after,
            "kwh_saved": self.kwh_saved,
            "co2_g_before": self.co2_g_before,
            "co2_g_after": self.co2_g_after,
            "co2_g_saved": self.co2_g_saved,
            "retention_score": self.retention_score,
            "model": self.model,
            "region": self.region,
            "strategy": self.strategy,
            "optimizations_applied": self.optimizations_applied or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<Receipt {self.receipt_id!r} saved={self.tokens_saved}>"
