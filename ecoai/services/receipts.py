"""Creating and ingesting optimization receipts."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select

from ecoai.extensions import db
from ecoai.models import Receipt, User
from ecoai.services.carbon import CarbonCalculator
from ecoai.services.optimizer import OptimizationResult

logger = logging.getLogger(__name__)

MAX_EVENTS_PER_BATCH = 500


class ReceiptValidationError(ValueError):
    """Raised when a submitted receipt cannot be accepted."""


@dataclass
class IngestReport:
    """Per-batch outcome. Rejections are reported rather than swallowed.

    The previous endpoint caught every exception, printed it, and still
    returned ``{"ok": true}``, so a client had no way to learn that its data
    had been dropped.
    """

    accepted: int = 0
    updated: int = 0
    rejected: list[dict] = field(default_factory=list)

    @property
    def total_rejected(self) -> int:
        return len(self.rejected)

    def to_dict(self) -> dict:
        return {
            "ok": not self.rejected,
            "accepted": self.accepted,
            "updated": self.updated,
            "rejected": self.rejected,
        }


def generate_receipt_id() -> str:
    return f"rcpt_{secrets.token_urlsafe(16)}"


def record_optimization(
    user: User,
    result: OptimizationResult,
    calculator: CarbonCalculator,
    *,
    model: str | None = None,
    region: str | None = None,
    receipt_id: str | None = None,
) -> Receipt:
    """Persist an optimization performed by the portal itself."""
    savings = calculator.savings(
        result.tokens_before, result.tokens_after, model=model, region=region
    )

    receipt = Receipt(
        receipt_id=receipt_id or generate_receipt_id(),
        user_id=user.id,
        tokens_before=result.tokens_before,
        tokens_after=result.tokens_after,
        kwh_before=savings.before.kwh,
        kwh_after=savings.after.kwh,
        co2_g_before=savings.before.co2_g,
        co2_g_after=savings.after.co2_g,
        retention_score=result.retention_score,
        model=model,
        region=region,
        strategy=result.strategy.value,
        optimizations_applied=[t.to_dict() for t in result.transformations],
    )
    db.session.add(receipt)
    return receipt


def ingest_batch(user: User, events: list[dict], calculator: CarbonCalculator) -> IngestReport:
    """Ingest receipts submitted by the SDK.

    Idempotent on ``receipt_id``: re-sending an event updates the stored row
    rather than duplicating it, so a client that retries after a timeout does
    not double-count its savings.
    """
    report = IngestReport()

    if len(events) > MAX_EVENTS_PER_BATCH:
        raise ReceiptValidationError(
            f"Batch contains {len(events)} events; the maximum is {MAX_EVENTS_PER_BATCH}."
        )

    for index, event in enumerate(events):
        # Validation for the whole event happens inside one guard so a single
        # malformed entry is rejected on its own rather than failing the batch
        # around it. Field-level problems raise from _receipt_fields, which is
        # why it sits inside the try and not after it.
        try:
            receipt_id, payload = _validate_event(event, index)

            existing = db.session.execute(
                select(Receipt).where(Receipt.receipt_id == receipt_id)
            ).scalar_one_or_none()

            if existing is not None and existing.user_id != user.id:
                # Receipt ids are global; refuse to let one account overwrite
                # another's row by guessing an id.
                raise ReceiptValidationError(
                    f"receipt_id {receipt_id!r} belongs to another account."
                )

            fields = _receipt_fields(payload, calculator)
        except ReceiptValidationError as exc:
            report.rejected.append({"index": index, "reason": str(exc)})
            continue

        if existing is None:
            db.session.add(Receipt(receipt_id=receipt_id, user_id=user.id, **fields))
            report.accepted += 1
        else:
            for key, value in fields.items():
                setattr(existing, key, value)
            report.updated += 1

    db.session.commit()

    if report.rejected:
        logger.warning(
            "Batch ingest completed with rejections",
            extra={
                "user_id": user.id,
                "accepted": report.accepted,
                "updated": report.updated,
                "rejected": report.total_rejected,
            },
        )
    return report


# -- Validation --------------------------------------------------------------


def _validate_event(event: object, index: int) -> tuple[str, dict]:
    if not isinstance(event, dict):
        raise ReceiptValidationError("Event must be an object.")

    if event.get("type") != "receipt":
        raise ReceiptValidationError(f"Unsupported event type {event.get('type')!r}.")

    receipt_id = event.get("receipt_id") or event.get("payload", {}).get("receipt_id")
    if not receipt_id or not isinstance(receipt_id, str):
        raise ReceiptValidationError("Missing receipt_id.")
    if len(receipt_id) > 128:
        raise ReceiptValidationError("receipt_id exceeds 128 characters.")

    payload = event.get("payload")
    if not isinstance(payload, dict) or not payload:
        raise ReceiptValidationError("Missing payload.")

    return receipt_id, payload


def _receipt_fields(payload: dict, calculator: CarbonCalculator) -> dict:
    tokens_before = _require_int(payload, "tokens_before")
    tokens_after = _require_int(payload, "tokens_after")

    if tokens_after > tokens_before:
        raise ReceiptValidationError(
            f"tokens_after ({tokens_after}) exceeds tokens_before ({tokens_before})."
        )

    route = payload.get("route") or {}
    if not isinstance(route, dict):
        raise ReceiptValidationError("route must be an object.")

    model = _optional_str(payload.get("model") or route.get("model"), "model", 64)
    region = _optional_str(payload.get("region") or route.get("region"), "region", 64)
    strategy = _optional_str(payload.get("strategy"), "strategy", 32)

    # Energy figures are recomputed from token counts unless the client sends
    # its own, so a client cannot inflate its reported savings by claiming an
    # arbitrary kwh_before.
    savings = calculator.savings(tokens_before, tokens_after, model=model, region=region)

    # `quality_score` is the pre-rename name; accepted so existing SDK
    # installations keep working.
    retention = payload.get("retention_score", payload.get("quality_score"))

    optimizations = payload.get("optimizations_applied", [])
    if not isinstance(optimizations, list):
        raise ReceiptValidationError("optimizations_applied must be an array.")

    return {
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "kwh_before": _float_or(payload.get("kwh_before"), savings.before.kwh),
        "kwh_after": _float_or(payload.get("kwh_after"), savings.after.kwh),
        "co2_g_before": _float_or(payload.get("co2_g_before"), savings.before.co2_g),
        "co2_g_after": _float_or(payload.get("co2_g_after"), savings.after.co2_g),
        "retention_score": _score_or_none(retention),
        "model": model,
        "region": region,
        "strategy": strategy,
        "optimizations_applied": optimizations[:50],
        "created_at": _parse_timestamp(payload.get("timestamp")),
    }


def _require_int(payload: dict, key: str) -> int:
    if key not in payload:
        raise ReceiptValidationError(f"Missing {key}.")
    try:
        value = int(payload[key])
    except (TypeError, ValueError) as exc:
        raise ReceiptValidationError(f"{key} must be an integer.") from exc
    if value < 0:
        raise ReceiptValidationError(f"{key} must be non-negative.")
    if value > 10_000_000:
        raise ReceiptValidationError(f"{key} is implausibly large ({value}).")
    return value


def _optional_str(value: object, key: str, max_length: int) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ReceiptValidationError(f"{key} must be a string.")
    trimmed = value.strip()
    if len(trimmed) > max_length:
        raise ReceiptValidationError(f"{key} exceeds {max_length} characters.")
    return trimmed or None


def _float_or(value: object, fallback: float) -> float:
    if value is None:
        return fallback
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _score_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return min(max(score, 0.0), 1.0)


def _parse_timestamp(value: object) -> datetime:
    """Accept ISO-8601 or epoch milliseconds; fall back to now."""
    now = datetime.now(UTC)
    if value is None:
        return now

    if isinstance(value, int | float):
        # Values past this threshold are milliseconds, not seconds.
        seconds = value / 1000 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return now

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return now
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    return now
