"""Unauthenticated pages: marketing, documentation, SDK download."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, render_template, send_file

from ecoai.services.carbon import MODEL_ACTIVE_PARAMS, REGION_GRID_INTENSITY
from ecoai.services.optimizer import Strategy

bp = Blueprint("public", __name__)

SDK_PATH = Path(__file__).resolve().parent.parent.parent / "sdk" / "ecoai_sdk.py"


@bp.route("/")
def home():
    return render_template("public/home.html")


@bp.route("/docs")
def docs():
    """API and SDK reference.

    The previous app registered ``/docs`` twice with two different view
    functions, so one template and its nine ``url_for('docs')`` links pointed
    at a page that could never render. There is one route now.
    """
    return render_template(
        "public/docs.html",
        strategies=list(Strategy),
        regions=sorted(REGION_GRID_INTENSITY.items(), key=lambda item: item[1]),
        models=sorted(MODEL_ACTIVE_PARAMS.items()),
        base_url=current_app.config["APP_BASE_URL"],
    )


@bp.route("/download")
def download():
    return render_template("public/download.html", base_url=current_app.config["APP_BASE_URL"])


@bp.route("/download/sdk")
def download_sdk():
    """Serve the SDK.

    It is a real file on disk under ``sdk/``, not a string literal embedded in
    a view function, so it can be linted, tested and imported like any other
    module.
    """
    return send_file(
        SDK_PATH,
        mimetype="text/x-python",
        as_attachment=True,
        download_name="ecoai_sdk.py",
    )


@bp.route("/healthz")
def healthz():
    """Liveness probe. Deliberately does not touch the database."""
    return {"status": "ok"}
