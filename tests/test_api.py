"""JSON API contract."""

from __future__ import annotations

import pytest

from ecoai.extensions import db
from ecoai.models import MlLearningEvent, MlPerformanceSnapshot, Receipt


@pytest.fixture
def api(client, user):
    """Client helper that always sends the user's API key."""

    class ApiClient:
        def __init__(self):
            self.headers = {"X-API-Key": user.api_key_secret}

        def get(self, path, **kwargs):
            return client.get(path, headers=self.headers, **kwargs)

        def post(self, path, **kwargs):
            return client.post(path, headers=self.headers, **kwargs)

    return ApiClient()


class TestIdentity:
    def test_me_returns_the_account(self, api, user):
        payload = api.get("/api/v1/me").get_json()
        assert payload["username"] == user.username
        assert payload["email"] == user.email
        assert payload["api_key_prefix"] == user.api_key_prefix

    def test_me_exposes_a_uuid_not_the_row_id(self, api, user):
        payload = api.get("/api/v1/me").get_json()
        assert payload["id"] == user.public_id
        assert payload["id"] != user.id
        assert len(payload["id"]) == 36

    def test_bearer_token_is_accepted(self, client, user):
        response = client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {user.api_key_secret}"}
        )
        assert response.status_code == 200


class TestOptimize:
    def test_optimizes_and_persists(self, api, user, app):
        response = api.post(
            "/api/v1/optimize",
            json={"prompt": "Could you please kindly summarize this?", "strategy": "balanced"},
        )
        assert response.status_code == 200

        payload = response.get_json()
        assert payload["tokens_after"] < payload["tokens_before"]
        assert payload["receipt_id"]
        assert 0.0 <= payload["retention_score"] <= 1.0
        assert payload["carbon"]["co2_g_saved"] > 0

        stored = db.session.query(Receipt).filter_by(receipt_id=payload["receipt_id"]).one()
        assert stored.user_id == user.id
        assert stored.tokens_before == payload["tokens_before"]

    def test_persist_false_records_nothing(self, api, app):
        before = db.session.query(Receipt).count()
        payload = api.post(
            "/api/v1/optimize", json={"prompt": "Please summarize.", "persist": False}
        ).get_json()

        assert payload["receipt_id"] is None
        assert db.session.query(Receipt).count() == before

    def test_missing_prompt_is_400(self, api):
        response = api.post("/api/v1/optimize", json={})
        assert response.status_code == 400
        assert response.get_json()["error"] == "invalid_request"

    def test_blank_prompt_is_400(self, api):
        assert api.post("/api/v1/optimize", json={"prompt": "   "}).status_code == 400

    def test_unknown_strategy_is_400_and_lists_valid_ones(self, api):
        response = api.post("/api/v1/optimize", json={"prompt": "hi", "strategy": "nuclear"})
        assert response.status_code == 400
        assert "conservative" in response.get_json()["message"]

    def test_oversized_prompt_is_rejected(self, api):
        response = api.post("/api/v1/optimize", json={"prompt": "x" * 50_001})
        assert response.status_code == 400
        assert "50000" in response.get_json()["message"]

    def test_region_changes_the_emissions_figure(self, api):
        dirty = api.post(
            "/api/v1/optimize",
            json={"prompt": "Please summarize.", "region": "ap-south-1", "persist": False},
        ).get_json()
        clean = api.post(
            "/api/v1/optimize",
            json={"prompt": "Please summarize.", "region": "eu-north-1", "persist": False},
        ).get_json()
        assert clean["carbon"]["co2_g_saved"] < dirty["carbon"]["co2_g_saved"]


class TestReceiptIngestion:
    def _event(self, receipt_id="r1", **overrides):
        payload = {"tokens_before": 100, "tokens_after": 60, "model": "gpt-4o-mini"}
        payload.update(overrides)
        return {"type": "receipt", "receipt_id": receipt_id, "payload": payload}

    def test_accepts_a_batch(self, api, app):
        response = api.post(
            "/api/v1/receipts/batch",
            json={"events": [self._event("a"), self._event("b")]},
        )
        assert response.status_code == 200

        payload = response.get_json()
        assert payload["accepted"] == 2
        assert payload["rejected"] == []
        assert db.session.query(Receipt).count() == 2

    def test_is_idempotent_on_receipt_id(self, api, app):
        api.post("/api/v1/receipts/batch", json={"events": [self._event("same")]})
        second = api.post("/api/v1/receipts/batch", json={"events": [self._event("same")]})

        assert second.get_json()["updated"] == 1
        assert second.get_json()["accepted"] == 0
        assert db.session.query(Receipt).count() == 1

    def test_partial_failure_reports_207_and_names_the_reason(self, api):
        response = api.post(
            "/api/v1/receipts/batch",
            json={
                "events": [
                    self._event("good"),
                    {"type": "receipt", "receipt_id": "bad", "payload": {"tokens_before": 10}},
                ]
            },
        )
        assert response.status_code == 207

        payload = response.get_json()
        assert payload["accepted"] == 1
        assert len(payload["rejected"]) == 1
        assert "tokens_after" in payload["rejected"][0]["reason"]

    def test_tokens_after_above_before_is_rejected(self, api):
        response = api.post(
            "/api/v1/receipts/batch",
            json={"events": [self._event("x", tokens_before=10, tokens_after=99)]},
        )
        assert response.status_code == 207
        assert "exceeds" in response.get_json()["rejected"][0]["reason"]

    def test_energy_is_recomputed_not_trusted(self, api, app):
        """A client must not be able to claim arbitrary savings."""
        api.post(
            "/api/v1/receipts/batch",
            json={
                "events": [
                    self._event("inflated", tokens_before=100, tokens_after=99, co2_g_before=None)
                ]
            },
        )
        stored = db.session.query(Receipt).filter_by(receipt_id="inflated").one()
        # One token of difference cannot produce a large saving.
        assert stored.co2_g_before - stored.co2_g_after < 0.01

    def test_empty_batch_is_accepted(self, api):
        response = api.post("/api/v1/receipts/batch", json={"events": []})
        assert response.status_code == 200
        assert response.get_json()["accepted"] == 0

    def test_events_must_be_an_array(self, api):
        assert api.post("/api/v1/receipts/batch", json={"events": "nope"}).status_code == 400

    def test_oversized_batch_is_rejected(self, api):
        events = [self._event(f"r{i}") for i in range(501)]
        response = api.post("/api/v1/receipts/batch", json={"events": events})
        assert response.status_code == 400
        assert "maximum" in response.get_json()["message"]

    def test_legacy_quality_score_key_is_accepted(self, api, app):
        api.post(
            "/api/v1/receipts/batch",
            json={"events": [self._event("legacy", quality_score=0.88)]},
        )
        stored = db.session.query(Receipt).filter_by(receipt_id="legacy").one()
        assert stored.retention_score == pytest.approx(0.88)


class TestMetrics:
    def test_summary_totals(self, api, user, make_receipts):
        make_receipts(user, count=4)
        payload = api.get("/api/v1/metrics/summary").get_json()

        assert payload["total_calls"] == 4
        assert payload["total_tokens_saved"] == 120  # 4 receipts x 30 saved
        assert payload["total_co2_g_saved"] > 0

    def test_summary_is_zero_for_a_new_account(self, api):
        payload = api.get("/api/v1/metrics/summary").get_json()
        assert payload["total_calls"] == 0
        assert payload["total_tokens_saved"] == 0

    def test_timeseries_fills_empty_days(self, api, user, make_receipts):
        make_receipts(user, count=2)
        payload = api.get("/api/v1/metrics/timeseries?days=7").get_json()

        assert len(payload["series"]) == 7
        assert sum(point["tokens_saved"] for point in payload["series"]) == 60

    def test_timeseries_window_slides_to_historical_data(self, api, user, make_receipts):
        """Regression: a trailing window showed zeroes for older accounts."""
        make_receipts(user, count=3, days_back=200)
        payload = api.get("/api/v1/metrics/timeseries?days=30").get_json()

        assert payload["is_historical_window"] is True
        assert sum(point["tokens_saved"] for point in payload["series"]) == 90

    def test_days_parameter_is_clamped(self, api):
        assert len(api.get("/api/v1/metrics/timeseries?days=9999").get_json()["series"]) == 365
        assert len(api.get("/api/v1/metrics/timeseries?days=-5").get_json()["series"]) == 1

    def test_model_breakdown_shares_sum_to_one(self, api, user, make_receipts):
        make_receipts(user, count=3, model="gpt-4o")
        make_receipts(user, count=1, days_back=1, model="claude-3-haiku")

        models = api.get("/api/v1/metrics/models").get_json()["models"]
        assert sum(entry["share"] for entry in models) == pytest.approx(1.0)
        assert models[0]["model"] == "gpt-4o"
        assert models[0]["calls"] == 3


class TestReceiptListing:
    def test_pagination(self, api, user, make_receipts):
        make_receipts(user, count=5)

        first = api.get("/api/v1/receipts?limit=2").get_json()
        assert len(first["receipts"]) == 2
        assert first["limit"] == 2

        second = api.get("/api/v1/receipts?limit=2&offset=2").get_json()
        assert first["receipts"][0]["receipt_id"] != second["receipts"][0]["receipt_id"]

    def test_limit_is_clamped(self, api, user, make_receipts):
        make_receipts(user, count=1)
        assert api.get("/api/v1/receipts?limit=99999").get_json()["limit"] == 500

    def test_garbage_limit_falls_back_to_default(self, api):
        assert api.get("/api/v1/receipts?limit=abc").get_json()["limit"] == 50


class TestTelemetry:
    def test_learning_event_is_stored(self, api, user, app):
        response = api.post(
            "/api/v1/ml/learning-events",
            json={"data": {"optimizationId": "opt-1", "promptFeatures": {"length": 42}}},
        )
        assert response.status_code == 201

        event = db.session.query(MlLearningEvent).one()
        assert event.user_id == user.id
        assert event.optimization_id == "opt-1"
        assert event.prompt_features == {"length": 42}

    def test_learning_event_requires_an_id(self, api):
        assert api.post("/api/v1/ml/learning-events", json={"data": {}}).status_code == 400

    def test_performance_snapshot_is_stored(self, api, user, app):
        response = api.post(
            "/api/v1/ml/performance-snapshots",
            json={"data": {"totalOptimizations": 10, "averageQuality": 0.9}},
        )
        assert response.status_code == 201

        snapshot = db.session.query(MlPerformanceSnapshot).one()
        assert snapshot.total_optimizations == 10
        assert snapshot.average_quality == pytest.approx(0.9)


class TestPublicReference:
    def test_regions_are_public_and_sorted(self, client):
        payload = client.get("/api/v1/carbon/regions").get_json()
        intensities = [entry["grid_intensity"] for entry in payload["regions"]]
        assert intensities == sorted(intensities)
        assert payload["unit"] == "gCO2eq/kWh"

    def test_healthz_does_not_touch_the_database(self, client):
        assert client.get("/healthz").get_json() == {"status": "ok"}
