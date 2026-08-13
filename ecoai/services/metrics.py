"""Dashboard and reporting aggregations.

Every query in this module is scoped to a single ``user_id``. That is the fix
for the previous dashboard, which ran ``SELECT * FROM receipts`` with no filter
and served one user's totals to whoever asked.

Bucketing happens in Python rather than SQL. ``DATE(col)`` is a SQLite
built-in with no PostgreSQL equivalent for timestamptz, so pushing it down
would need dialect-specific branches for a per-user row count in the hundreds.
If receipt volume ever makes that the bottleneck, replace
:func:`_bucket_by_day` with ``date_trunc``/``strftime`` behind a dialect check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

from ecoai.extensions import db
from ecoai.models import Receipt
from ecoai.services.pricing import cost_saved_usd


@dataclass
class DailyPoint:
    day: date
    tokens_saved: int = 0
    co2_g_saved: float = 0.0
    cost_saved_usd: float = 0.0
    calls: int = 0


@dataclass
class ModelUsage:
    model: str
    calls: int
    share: float
    tokens_saved: int
    co2_g_saved: float
    cost_saved_usd: float

    @property
    def avg_tokens_saved(self) -> float:
        return self.tokens_saved / self.calls if self.calls else 0.0


@dataclass
class MetricsSummary:
    """All-time totals for one user."""

    total_calls: int = 0
    total_tokens_before: int = 0
    total_tokens_after: int = 0
    total_tokens_saved: int = 0
    total_co2_g_saved: float = 0.0
    total_kwh_saved: float = 0.0
    total_cost_saved_usd: float = 0.0
    avg_retention_score: float | None = None
    first_receipt_at: datetime | None = None
    last_receipt_at: datetime | None = None

    @property
    def avg_tokens_before(self) -> float:
        return self.total_tokens_before / self.total_calls if self.total_calls else 0.0

    @property
    def avg_tokens_after(self) -> float:
        return self.total_tokens_after / self.total_calls if self.total_calls else 0.0

    @property
    def reduction_ratio(self) -> float:
        return self.total_tokens_saved / self.total_tokens_before if self.total_tokens_before else 0.0

    def to_dict(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "total_tokens_saved": self.total_tokens_saved,
            "total_co2_g_saved": self.total_co2_g_saved,
            "total_kwh_saved": self.total_kwh_saved,
            "total_cost_saved_usd": self.total_cost_saved_usd,
            "avg_tokens_before": self.avg_tokens_before,
            "avg_tokens_after": self.avg_tokens_after,
            "reduction_ratio": self.reduction_ratio,
            "avg_retention_score": self.avg_retention_score,
            "first_receipt_at": self.first_receipt_at.isoformat() if self.first_receipt_at else None,
            "last_receipt_at": self.last_receipt_at.isoformat() if self.last_receipt_at else None,
        }


@dataclass
class DashboardData:
    """Everything the dashboard template renders."""

    summary: MetricsSummary = field(default_factory=MetricsSummary)
    timeseries: list[DailyPoint] = field(default_factory=list)
    model_usage: list[ModelUsage] = field(default_factory=list)
    region_usage: list[tuple[str, int]] = field(default_factory=list)
    recent_receipts: list[Receipt] = field(default_factory=list)
    #: True when the chart window was moved back to where the data actually is.
    window_is_historical: bool = False
    window_start: date | None = None
    window_end: date | None = None

    @property
    def has_data(self) -> bool:
        return self.summary.total_calls > 0


def get_summary(user_id: int) -> MetricsSummary:
    """All-time totals for one user, computed in the database."""
    row = db.session.execute(
        select(
            func.count(Receipt.id),
            func.coalesce(func.sum(Receipt.tokens_before), 0),
            func.coalesce(func.sum(Receipt.tokens_after), 0),
            func.coalesce(func.sum(Receipt.co2_g_before - Receipt.co2_g_after), 0.0),
            func.coalesce(func.sum(Receipt.kwh_before - Receipt.kwh_after), 0.0),
            func.avg(Receipt.retention_score),
            func.min(Receipt.created_at),
            func.max(Receipt.created_at),
        ).where(Receipt.user_id == user_id)
    ).one()

    calls, tokens_before, tokens_after, co2_saved, kwh_saved, avg_retention, first, last = row

    summary = MetricsSummary(
        total_calls=calls or 0,
        total_tokens_before=int(tokens_before or 0),
        total_tokens_after=int(tokens_after or 0),
        total_tokens_saved=int((tokens_before or 0) - (tokens_after or 0)),
        total_co2_g_saved=float(co2_saved or 0.0),
        total_kwh_saved=float(kwh_saved or 0.0),
        avg_retention_score=float(avg_retention) if avg_retention is not None else None,
        first_receipt_at=first,
        last_receipt_at=last,
    )

    # Cost depends on per-receipt model pricing, so it needs the grouped rows.
    summary.total_cost_saved_usd = sum(
        cost_saved_usd(int(tokens_saved or 0), model)
        for model, tokens_saved in db.session.execute(
            select(
                Receipt.model,
                func.sum(Receipt.tokens_before - Receipt.tokens_after),
            )
            .where(Receipt.user_id == user_id)
            .group_by(Receipt.model)
        ).all()
    )
    return summary


def get_model_usage(user_id: int) -> list[ModelUsage]:
    """Per-model breakdown over all time.

    The previous dashboard computed this inside a seven-day loop while deriving
    the percentage from the all-time call count, so the two panels disagreed
    whenever any receipt was older than a week. Both are all-time here.
    """
    rows = db.session.execute(
        select(
            Receipt.model,
            func.count(Receipt.id),
            func.coalesce(func.sum(Receipt.tokens_before - Receipt.tokens_after), 0),
            func.coalesce(func.sum(Receipt.co2_g_before - Receipt.co2_g_after), 0.0),
        )
        .where(Receipt.user_id == user_id)
        .group_by(Receipt.model)
        .order_by(func.count(Receipt.id).desc())
    ).all()

    total_calls = sum(row[1] for row in rows)
    return [
        ModelUsage(
            model=model or "unspecified",
            calls=calls,
            share=calls / total_calls if total_calls else 0.0,
            tokens_saved=int(tokens_saved or 0),
            co2_g_saved=float(co2_saved or 0.0),
            cost_saved_usd=cost_saved_usd(int(tokens_saved or 0), model),
        )
        for model, calls, tokens_saved, co2_saved in rows
    ]


def get_region_usage(user_id: int) -> list[tuple[str, int]]:
    rows = db.session.execute(
        select(Receipt.region, func.count(Receipt.id))
        .where(Receipt.user_id == user_id)
        .group_by(Receipt.region)
        .order_by(func.count(Receipt.id).desc())
    ).all()
    return [(region or "unspecified", count) for region, count in rows]


def get_timeseries(
    user_id: int, days: int = 30, *, anchor: datetime | None = None
) -> tuple[list[DailyPoint], bool]:
    """Daily savings over a window, with empty days filled in.

    Returns ``(points, is_historical)``. When the user has receipts but none
    inside the trailing window, the window slides back to end at their most
    recent receipt and ``is_historical`` is True, so the chart shows the data
    that exists rather than a flat line of zeros.
    """
    anchor = anchor or datetime.now(UTC)
    window_start = anchor - timedelta(days=days - 1)

    receipts = _receipts_since(user_id, window_start)
    is_historical = False

    if not receipts:
        latest = db.session.execute(
            select(func.max(Receipt.created_at)).where(Receipt.user_id == user_id)
        ).scalar()
        if latest is not None:
            anchor = _ensure_aware(latest)
            window_start = anchor - timedelta(days=days - 1)
            receipts = _receipts_since(user_id, window_start)
            is_historical = bool(receipts)

    buckets = _bucket_by_day(receipts)
    points = [
        buckets.get(
            (window_start + timedelta(days=offset)).date(),
            DailyPoint(day=(window_start + timedelta(days=offset)).date()),
        )
        for offset in range(days)
    ]
    return points, is_historical


def get_recent_receipts(user_id: int, limit: int = 25) -> list[Receipt]:
    return list(
        db.session.execute(
            select(Receipt)
            .where(Receipt.user_id == user_id)
            .order_by(Receipt.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def build_dashboard(user_id: int, *, days: int = 30, recent_limit: int = 25) -> DashboardData:
    """Assemble the full dashboard payload for one user."""
    timeseries, is_historical = get_timeseries(user_id, days=days)
    return DashboardData(
        summary=get_summary(user_id),
        timeseries=timeseries,
        model_usage=get_model_usage(user_id),
        region_usage=get_region_usage(user_id),
        recent_receipts=get_recent_receipts(user_id, limit=recent_limit),
        window_is_historical=is_historical,
        window_start=timeseries[0].day if timeseries else None,
        window_end=timeseries[-1].day if timeseries else None,
    )


# -- Internals ---------------------------------------------------------------


def _receipts_since(user_id: int, since: datetime) -> list[Receipt]:
    return list(
        db.session.execute(
            select(Receipt)
            .where(Receipt.user_id == user_id, Receipt.created_at >= since)
            .order_by(Receipt.created_at)
        )
        .scalars()
        .all()
    )


def _bucket_by_day(receipts: list[Receipt]) -> dict[date, DailyPoint]:
    buckets: dict[date, DailyPoint] = {}
    for receipt in receipts:
        day = _ensure_aware(receipt.created_at).date()
        point = buckets.setdefault(day, DailyPoint(day=day))
        point.tokens_saved += receipt.tokens_saved
        point.co2_g_saved += receipt.co2_g_saved
        point.cost_saved_usd += cost_saved_usd(receipt.tokens_saved, receipt.model)
        point.calls += 1
    return buckets


def _ensure_aware(value: datetime) -> datetime:
    """Attach UTC to naive datetimes.

    SQLite has no timestamptz, so values written as aware read back naive.
    Comparing those against aware datetimes raises, hence this normalization.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
