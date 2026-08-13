"""Signed-in dashboard.

Every figure here is scoped to ``current_user``. The previous implementation
had its session check commented out and queried the receipts table with no
user filter, so an anonymous visitor was served the whole table's totals.
"""

from __future__ import annotations

import csv
import io
import logging

from flask import Blueprint, Response, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from ecoai.extensions import limiter
from ecoai.forms import SendReportForm
from ecoai.services import metrics
from ecoai.services.mailer import MailError, Message

logger = logging.getLogger(__name__)

bp = Blueprint("dashboard", __name__)


@bp.route("/dashboard")
@login_required
def index():
    data = metrics.build_dashboard(current_user.id)
    return render_template(
        "dashboard/index.html",
        data=data,
        report_form=SendReportForm(),
        chart={
            "labels": [point.day.strftime("%b %d") for point in data.timeseries],
            "tokens": [point.tokens_saved for point in data.timeseries],
            "co2": [round(point.co2_g_saved, 6) for point in data.timeseries],
            "cost": [round(point.cost_saved_usd, 6) for point in data.timeseries],
        },
    )


@bp.route("/dashboard/export.csv")
@login_required
def export_csv():
    """Download this account's receipts.

    Written with :mod:`csv` so values containing commas or quotes are escaped.
    The previous export built the file by string concatenation and emitted
    columns that did not match its own header row.
    """
    receipts = metrics.get_recent_receipts(current_user.id, limit=10_000)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "receipt_id",
            "created_at",
            "model",
            "region",
            "strategy",
            "tokens_before",
            "tokens_after",
            "tokens_saved",
            "kwh_before",
            "kwh_after",
            "co2_g_before",
            "co2_g_after",
            "co2_g_saved",
            "retention_score",
        ]
    )
    for receipt in receipts:
        writer.writerow(
            [
                receipt.receipt_id,
                receipt.created_at.isoformat() if receipt.created_at else "",
                receipt.model or "",
                receipt.region or "",
                receipt.strategy or "",
                receipt.tokens_before,
                receipt.tokens_after,
                receipt.tokens_saved,
                f"{receipt.kwh_before:.10f}",
                f"{receipt.kwh_after:.10f}",
                f"{receipt.co2_g_before:.10f}",
                f"{receipt.co2_g_after:.10f}",
                f"{receipt.co2_g_saved:.10f}",
                "" if receipt.retention_score is None else f"{receipt.retention_score:.4f}",
            ]
        )

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ecoai-receipts.csv"},
    )


@bp.route("/dashboard/report", methods=["POST"])
@login_required
@limiter.limit(lambda: current_app.config["ECOAI"].ratelimit_email)
def email_report():
    """Email the impact report to the signed-in account's own address.

    There is no recipient parameter. The previous endpoint accepted an
    arbitrary address from an unauthenticated form and mailed it aggregate
    statistics for every user in the database.
    """
    form = SendReportForm()
    if not form.validate_on_submit():
        flash("That request could not be verified. Please try again.", "error")
        return redirect(url_for("dashboard.index"))

    data = metrics.build_dashboard(current_user.id)
    if not data.has_data:
        flash("You have no optimizations to report yet.", "info")
        return redirect(url_for("dashboard.index"))

    mailer = current_app.extensions["ecoai_mailer"]
    message = Message(
        to=current_user.email,
        subject=f"Your EcoAI impact report — {data.summary.total_co2_g_saved:.3f} g CO₂ saved",
        text_body=render_template("email/impact_report.txt", user=current_user, data=data),
        html_body=render_template("email/impact_report.html", user=current_user, data=data),
    )

    try:
        mailer.send(message)
    except MailError:
        flash("We could not send that email right now. Please try again later.", "error")
        return redirect(url_for("dashboard.index"))

    if mailer.enabled:
        flash(f"Impact report sent to {current_user.email}.", "success")
    else:
        flash(
            "Email delivery is disabled in this environment; the report was rendered to the logs.",
            "info",
        )
    return redirect(url_for("dashboard.index"))
