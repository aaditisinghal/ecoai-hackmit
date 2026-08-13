"""Dashboard pages, CSV export and the metrics aggregation behind them."""

from __future__ import annotations

import csv
import io
import itertools

import pytest

from ecoai.services import metrics


class TestDashboardPage:
    def test_empty_state_for_a_new_account(self, auth_client):
        body = auth_client.get("/dashboard").get_data(as_text=True)
        assert "No optimizations yet" in body

    def test_renders_totals(self, auth_client, user, make_receipts):
        make_receipts(user, count=4)
        body = auth_client.get("/dashboard").get_data(as_text=True)

        assert "120" in body  # 4 x 30 tokens saved
        assert "No optimizations yet" not in body

    def test_historical_window_is_explained_to_the_user(self, auth_client, user, make_receipts):
        make_receipts(user, count=2, days_back=300)
        body = auth_client.get("/dashboard").get_data(as_text=True)
        assert "most recent optimization" in body


class TestCsvExport:
    def test_requires_authentication(self, client):
        response = client.get("/dashboard/export.csv", follow_redirects=False)
        assert response.status_code == 302

    def test_header_matches_the_rows(self, auth_client, user, make_receipts):
        """Regression: the old export's header and columns did not correspond."""
        make_receipts(user, count=3)

        response = auth_client.get("/dashboard/export.csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers["Content-Type"]

        rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
        assert len(rows) == 3

        for row in rows:
            assert row["receipt_id"].startswith("rcpt-")
            assert int(row["tokens_before"]) == int(row["tokens_after"]) + int(row["tokens_saved"])
            assert float(row["co2_g_before"]) > float(row["co2_g_after"])

    def test_only_exports_your_own_receipts(self, auth_client, user, make_user, make_receipts):
        other, _ = make_user("someone-else")
        make_receipts(user, count=2)
        make_receipts(other, count=5)

        body = auth_client.get("/dashboard/export.csv").get_data(as_text=True)
        rows = list(csv.DictReader(io.StringIO(body)))
        assert len(rows) == 2

    def test_values_containing_commas_are_escaped(self, auth_client, user, make_receipts, app):
        from ecoai.extensions import db

        receipts = make_receipts(user, count=1)
        receipts[0].model = "model,with,commas"
        db.session.commit()

        body = auth_client.get("/dashboard/export.csv").get_data(as_text=True)
        rows = list(csv.DictReader(io.StringIO(body)))
        assert rows[0]["model"] == "model,with,commas"


class TestEmailReport:
    def test_sends_to_the_account_owner(self, auth_client, user, make_receipts, app):
        make_receipts(user, count=2)

        sent = []
        app.extensions["ecoai_mailer"].send = lambda message: sent.append(message) or True

        auth_client.post("/dashboard/report", follow_redirects=True)

        assert len(sent) == 1
        assert sent[0].to == user.email
        assert "CO₂" in sent[0].subject
        assert user.username in sent[0].text_body
        assert sent[0].html_body is not None

    def test_no_data_means_no_email(self, auth_client, app):
        sent = []
        app.extensions["ecoai_mailer"].send = lambda message: sent.append(message) or True

        response = auth_client.post("/dashboard/report", follow_redirects=True)
        assert sent == []
        assert "no optimizations to report" in response.get_data(as_text=True).lower()

    def test_delivery_failure_is_surfaced_not_swallowed(self, auth_client, user, make_receipts, app):
        from ecoai.services.mailer import MailError

        make_receipts(user, count=1)

        def explode(message):
            raise MailError("smtp down")

        app.extensions["ecoai_mailer"].send = explode

        response = auth_client.post("/dashboard/report", follow_redirects=True)
        assert "could not send that email" in response.get_data(as_text=True).lower()


class TestMetricsAggregation:
    def test_summary_is_scoped_per_user(self, app, make_user, make_receipts):
        alice, _ = make_user("alice3")
        bob, _ = make_user("bob3")
        make_receipts(alice, count=2)
        make_receipts(bob, count=5)

        assert metrics.get_summary(alice.id).total_calls == 2
        assert metrics.get_summary(bob.id).total_calls == 5

    def test_averages(self, app, user, make_receipts):
        make_receipts(user, count=4)
        summary = metrics.get_summary(user.id)

        assert summary.avg_tokens_before == pytest.approx(101.5)  # 100..103
        assert summary.avg_tokens_after == pytest.approx(71.5)
        assert summary.avg_retention_score == pytest.approx(0.95)

    def test_reduction_ratio(self, app, user, make_receipts):
        make_receipts(user, count=2)
        summary = metrics.get_summary(user.id)
        assert summary.reduction_ratio == pytest.approx(60 / 201)

    def test_empty_account_has_zero_totals(self, app, user):
        summary = metrics.get_summary(user.id)
        assert summary.total_calls == 0
        assert summary.total_tokens_saved == 0
        assert summary.avg_retention_score is None
        assert summary.reduction_ratio == 0.0

    def test_timeseries_length_matches_requested_days(self, app, user, make_receipts):
        make_receipts(user, count=1)
        points, _ = metrics.get_timeseries(user.id, days=14)
        assert len(points) == 14

    def test_timeseries_days_are_consecutive(self, app, user, make_receipts):
        make_receipts(user, count=1)
        points, _ = metrics.get_timeseries(user.id, days=10)
        for earlier, later in itertools.pairwise(points):
            assert (later.day - earlier.day).days == 1

    def test_timeseries_is_not_historical_for_recent_data(self, app, user, make_receipts):
        make_receipts(user, count=1)
        _, is_historical = metrics.get_timeseries(user.id, days=30)
        assert is_historical is False

    def test_timeseries_is_empty_for_a_new_account(self, app, user):
        points, is_historical = metrics.get_timeseries(user.id, days=7)
        assert len(points) == 7
        assert all(point.tokens_saved == 0 for point in points)
        assert is_historical is False

    def test_model_usage_and_summary_agree_on_call_count(self, app, user, make_receipts):
        """Regression: the two panels used different windows and disagreed."""
        make_receipts(user, count=3, model="gpt-4o")
        make_receipts(user, count=2, days_back=400, model="claude-3-haiku")

        summary = metrics.get_summary(user.id)
        usage = metrics.get_model_usage(user.id)

        assert sum(entry.calls for entry in usage) == summary.total_calls == 5

    def test_region_usage_labels_missing_regions(self, app, user, make_receipts):
        from ecoai.extensions import db

        receipts = make_receipts(user, count=1)
        receipts[0].region = None
        db.session.commit()

        assert metrics.get_region_usage(user.id) == [("unspecified", 1)]

    def test_build_dashboard_assembles_everything(self, app, user, make_receipts):
        make_receipts(user, count=3)
        data = metrics.build_dashboard(user.id)

        assert data.has_data
        assert data.summary.total_calls == 3
        assert len(data.timeseries) == 30
        assert len(data.recent_receipts) == 3
        assert data.window_start is not None and data.window_end is not None
