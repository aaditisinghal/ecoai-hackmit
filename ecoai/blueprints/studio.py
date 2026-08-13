"""Prompt Studio.

The page is a thin shell; the work happens in ``POST /api/v1/optimize``. The
previous version optimized entirely in the browser behind a fake 1.5 second
delay and never contacted the server, so nothing it showed was recorded and
its "quality score" was ``0.95 + Math.random() * 0.04``.
"""

from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import login_required

from ecoai.forms import OptimizeForm
from ecoai.services.carbon import REGION_GRID_INTENSITY

bp = Blueprint("studio", __name__)


@bp.route("/studio")
@login_required
def index():
    return render_template(
        "studio/index.html",
        form=OptimizeForm(),
        regions=sorted(REGION_GRID_INTENSITY.items(), key=lambda item: item[1]),
    )
