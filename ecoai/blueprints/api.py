"""Versioned JSON API.

Mounted at ``/api/v1``. Every route is scoped to the authenticated account,
returns JSON, and reports failures with a machine-readable ``error`` code
rather than a bare string.

The blueprint is exempt from the global CSRF hook because it is primarily
token-authenticated; requests that fall back to a session cookie have their
CSRF token validated explicitly in
:func:`ecoai.security.api_key_or_session_required`.
"""

from __future__ import annotations

import logging

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import select

from ecoai.extensions import db, limiter
from ecoai.models import MlLearningEvent, MlPerformanceSnapshot, Receipt
from ecoai.security import api_key_or_session_required, api_key_required
from ecoai.services import metrics
from ecoai.services.carbon import REGION_GRID_INTENSITY
from ecoai.services.optimizer import Strategy, optimizer
from ecoai.services.receipts import (
    ReceiptValidationError,
    ingest_batch,
    record_optimization,
)

logger = logging.getLogger(__name__)

bp = Blueprint("api", __name__, url_prefix="/api/v1")

MAX_PROMPT_CHARS = 50_000


@bp.before_request
def _apply_rate_limit():
    """Rate limits are configured per-deployment, so bind them at request time."""
    return None


def _error(code: str, message: str, status: int):
    return jsonify({"error": code, "message": message}), status


def _json_body() -> dict:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _carbon():
    return current_app.extensions["ecoai_carbon"]


# --- Identity ---------------------------------------------------------------


@bp.get("/me")
@api_key_or_session_required
def me():
    user = g.api_user
    return jsonify(
        {
            "id": user.public_id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin,
            "api_key_prefix": user.api_key_prefix,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
    )


# --- Optimization -----------------------------------------------------------


@bp.post("/optimize")
@api_key_or_session_required
@limiter.limit(lambda: current_app.config["ECOAI"].ratelimit_api)
def optimize():
    """Optimize a prompt and, unless asked not to, record a receipt.

    This is the endpoint the Prompt Studio calls. The studio previously ran a
    ``setTimeout`` and a client-side regex, so nothing it displayed had ever
    touched the server or been persisted.
    """
    body = _json_body()
    prompt = body.get("prompt")

    if not isinstance(prompt, str) or not prompt.strip():
        return _error("invalid_request", "Field 'prompt' is required.", 400)
    if len(prompt) > MAX_PROMPT_CHARS:
        return _error(
            "invalid_request",
            f"Prompt is {len(prompt)} characters; the limit is {MAX_PROMPT_CHARS}.",
            400,
        )

    try:
        strategy = Strategy.parse(body.get("strategy"))
    except ValueError as exc:
        return _error("invalid_request", str(exc), 400)

    model = body.get("model") or None
    region = body.get("region") or None
    persist = body.get("persist", True)

    result = optimizer.optimize(prompt, strategy)
    savings = _carbon().savings(
        result.tokens_before, result.tokens_after, model=model, region=region
    )

    payload = result.to_dict()
    payload["carbon"] = savings.to_dict()
    payload["model"] = model
    payload["region"] = region

    if persist:
        receipt = record_optimization(
            g.api_user, result, _carbon(), model=model, region=region
        )
        db.session.commit()
        payload["receipt_id"] = receipt.receipt_id
    else:
        payload["receipt_id"] = None

    return jsonify(payload)


# --- Receipts ---------------------------------------------------------------


@bp.post("/receipts/batch")
@api_key_required
@limiter.limit(lambda: current_app.config["ECOAI"].ratelimit_api)
def ingest_receipts():
    """Ingest a batch of receipts from the SDK."""
    body = _json_body()
    events = body.get("events")

    if not isinstance(events, list):
        return _error("invalid_request", "Field 'events' must be an array.", 400)
    if not events:
        return jsonify({"ok": True, "accepted": 0, "updated": 0, "rejected": []})

    try:
        report = ingest_batch(g.api_user, events, _carbon())
    except ReceiptValidationError as exc:
        return _error("invalid_request", str(exc), 400)

    # Partial success is reported as 207 so a client can tell the difference
    # between "all stored" and "some dropped" without parsing the body.
    status = 207 if report.rejected else 200
    return jsonify(report.to_dict()), status


@bp.get("/receipts")
@api_key_or_session_required
def list_receipts():
    limit = min(max(_int_arg("limit", 50), 1), 500)
    offset = max(_int_arg("offset", 0), 0)

    receipts = (
        db.session.execute(
            select(Receipt)
            .where(Receipt.user_id == g.api_user.id)
            .order_by(Receipt.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    # Objects, not raw tuples. The previous endpoint returned positional arrays
    # that leaked the internal row id and user_id, and broke any client the
    # moment a column was added.
    return jsonify(
        {
            "receipts": [receipt.to_dict() for receipt in receipts],
            "limit": limit,
            "offset": offset,
        }
    )


# --- Metrics ----------------------------------------------------------------


@bp.get("/metrics/summary")
@api_key_or_session_required
def metrics_summary():
    return jsonify(metrics.get_summary(g.api_user.id).to_dict())


@bp.get("/metrics/timeseries")
@api_key_or_session_required
def metrics_timeseries():
    days = min(max(_int_arg("days", 30), 1), 365)
    points, is_historical = metrics.get_timeseries(g.api_user.id, days=days)
    return jsonify(
        {
            "days": days,
            "is_historical_window": is_historical,
            "series": [
                {
                    "day": point.day.isoformat(),
                    "calls": point.calls,
                    "tokens_saved": point.tokens_saved,
                    "co2_g_saved": point.co2_g_saved,
                    "cost_saved_usd": point.cost_saved_usd,
                }
                for point in points
            ],
        }
    )


@bp.get("/metrics/models")
@api_key_or_session_required
def metrics_models():
    return jsonify(
        {
            "models": [
                {
                    "model": usage.model,
                    "calls": usage.calls,
                    "share": usage.share,
                    "tokens_saved": usage.tokens_saved,
                    "co2_g_saved": usage.co2_g_saved,
                    "cost_saved_usd": usage.cost_saved_usd,
                }
                for usage in metrics.get_model_usage(g.api_user.id)
            ]
        }
    )


# --- Carbon reference -------------------------------------------------------


@bp.get("/carbon/regions")
def carbon_regions():
    """Grid intensities used by the estimator. Public reference data."""
    return jsonify(
        {
            "unit": "gCO2eq/kWh",
            "note": "Static annual averages. Wire in ElectricityMaps or WattTime for live values.",
            "regions": [
                {"region": region, "grid_intensity": intensity}
                for region, intensity in sorted(
                    REGION_GRID_INTENSITY.items(), key=lambda item: item[1]
                )
            ],
        }
    )


# --- SDK telemetry ----------------------------------------------------------


@bp.post("/ml/learning-events")
@api_key_required
def ingest_learning_event():
    body = _json_body()
    data = body.get("data") if isinstance(body.get("data"), dict) else body

    optimization_id = data.get("optimizationId") or data.get("optimization_id")
    if not optimization_id:
        return _error("invalid_request", "Field 'optimizationId' is required.", 400)

    db.session.add(
        MlLearningEvent(
            user_id=g.api_user.id,
            optimization_id=str(optimization_id)[:128],
            prompt_features=_as_dict(data.get("promptFeatures") or data.get("prompt_features")),
            optimization_result=_as_dict(
                data.get("optimizationResult") or data.get("optimization_result")
            ),
            quality_metrics=_as_dict(data.get("qualityMetrics") or data.get("quality_metrics")),
            user_feedback=_as_text(data.get("userFeedback") or data.get("user_feedback")),
            observed_at=_observed_at(data.get("timestamp")),
        )
    )
    db.session.commit()
    return jsonify({"ok": True, "optimization_id": optimization_id}), 201


@bp.post("/ml/performance-snapshots")
@api_key_required
def ingest_performance_snapshot():
    body = _json_body()
    data = body.get("data") if isinstance(body.get("data"), dict) else body

    db.session.add(
        MlPerformanceSnapshot(
            user_id=g.api_user.id,
            total_optimizations=_as_int(data.get("totalOptimizations")),
            average_quality=_as_float(data.get("averageQuality")),
            average_token_reduction=_as_float(data.get("averageTokenReduction")),
            success_rate=_as_float(data.get("successRate")),
            quality_trend=_as_float(data.get("qualityTrend")),
            observed_at=_observed_at(data.get("timestamp")),
        )
    )
    db.session.commit()
    return jsonify({"ok": True}), 201


# --- Helpers ----------------------------------------------------------------


def _int_arg(name: str, default: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _as_text(value) -> str | None:
    return value[:5000] if isinstance(value, str) else None


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _observed_at(value):
    from ecoai.services.receipts import _parse_timestamp

    return _parse_timestamp(value) if value is not None else None
