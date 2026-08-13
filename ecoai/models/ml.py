"""Telemetry the SDK reports back for offline analysis.

These tables are write-mostly. Nothing in the request path reads them; they
exist so optimization strategies can be evaluated against real usage later.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ecoai.models.base import Base, utcnow


class MlLearningEvent(Base):
    """A single optimization with its inputs, outputs and any user feedback."""

    __tablename__ = "ml_learning_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    optimization_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    prompt_features: Mapped[dict | None] = mapped_column(JSON, default=dict)
    optimization_result: Mapped[dict | None] = mapped_column(JSON, default=dict)
    quality_metrics: Mapped[dict | None] = mapped_column(JSON, default=dict)
    user_feedback: Mapped[str | None] = mapped_column(Text, default=None)

    # When the SDK observed the event, as opposed to when we stored it.
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )


class MlPerformanceSnapshot(Base):
    """Periodic rollup of how an SDK instance is performing."""

    __tablename__ = "ml_performance_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    total_optimizations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_quality: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    average_token_reduction: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    success_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    quality_trend: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
