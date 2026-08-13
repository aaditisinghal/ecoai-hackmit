"""Administration.

Access is granted by the ``users.is_admin`` column and the normal login
session. There is no separate admin password: the previous implementation
compared the submitted credentials against a fixed username and password pair
written into the source file, and its user list rendered every account's full
API key on screen.

API keys are now stored as digests, so there is nothing here that could
display one even if it wanted to.
"""

from __future__ import annotations

import csv
import io
import logging

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, select

from ecoai.extensions import db
from ecoai.forms import AdminUserActionForm
from ecoai.models import Receipt, User
from ecoai.security import admin_required

logger = logging.getLogger(__name__)

bp = Blueprint("admin", __name__, url_prefix="/admin")

PAGE_SIZE = 50


@bp.route("/")
@admin_required
def index():
    totals = db.session.execute(
        select(
            func.count(Receipt.id),
            func.coalesce(func.sum(Receipt.tokens_before - Receipt.tokens_after), 0),
            func.coalesce(func.sum(Receipt.co2_g_before - Receipt.co2_g_after), 0.0),
        )
    ).one()

    user_count = db.session.execute(select(func.count(User.id))).scalar_one()
    active_count = db.session.execute(
        select(func.count(User.id)).where(User.is_active.is_(True))
    ).scalar_one()

    recent_users = (
        db.session.execute(select(User).order_by(User.created_at.desc()).limit(10)).scalars().all()
    )
    recent_receipts = (
        db.session.execute(select(Receipt).order_by(Receipt.created_at.desc()).limit(10))
        .scalars()
        .all()
    )

    return render_template(
        "admin/index.html",
        total_users=user_count,
        active_users=active_count,
        total_receipts=totals[0],
        total_tokens_saved=int(totals[1] or 0),
        total_co2_saved=float(totals[2] or 0.0),
        recent_users=recent_users,
        recent_receipts=recent_receipts,
    )


@bp.route("/users")
@admin_required
def users():
    page = max(request.args.get("page", 1, type=int), 1)
    query = request.args.get("q", "").strip()

    statement = select(User).order_by(User.created_at.desc())
    if query:
        pattern = f"%{query.lower()}%"
        statement = statement.where(
            func.lower(User.username).like(pattern) | func.lower(User.email).like(pattern)
        )

    total = db.session.execute(
        select(func.count()).select_from(statement.subquery())
    ).scalar_one()

    rows = (
        db.session.execute(statement.limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE))
        .scalars()
        .all()
    )

    return render_template(
        "admin/users.html",
        users=rows,
        form=AdminUserActionForm(),
        page=page,
        page_size=PAGE_SIZE,
        total=total,
        query=query,
    )


@bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@admin_required
def toggle_active(user_id: int):
    form = AdminUserActionForm()
    if not form.validate_on_submit():
        abort(400)

    user = db.session.get(User, user_id)
    if user is None:
        abort(404)

    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin.users"))

    user.is_active = not user.is_active
    db.session.commit()
    logger.info(
        "Admin toggled account state",
        extra={"admin_id": current_user.id, "user_id": user.id, "is_active": user.is_active},
    )

    flash(
        f"{user.username} is now {'active' if user.is_active else 'deactivated'}.",
        "success",
    )
    return redirect(url_for("admin.users", page=request.args.get("page", 1)))


@bp.route("/users/<int:user_id>/toggle-admin", methods=["POST"])
@admin_required
def toggle_admin(user_id: int):
    form = AdminUserActionForm()
    if not form.validate_on_submit():
        abort(400)

    user = db.session.get(User, user_id)
    if user is None:
        abort(404)

    if user.id == current_user.id:
        flash("You cannot change your own administrator status.", "error")
        return redirect(url_for("admin.users"))

    user.is_admin = not user.is_admin
    db.session.commit()
    logger.info(
        "Admin changed administrator status",
        extra={"admin_id": current_user.id, "user_id": user.id, "is_admin": user.is_admin},
    )

    flash(
        f"{user.username} is {'now an administrator' if user.is_admin else 'no longer an administrator'}.",
        "success",
    )
    return redirect(url_for("admin.users", page=request.args.get("page", 1)))


@bp.route("/receipts")
@admin_required
def receipts():
    page = max(request.args.get("page", 1, type=int), 1)

    total = db.session.execute(select(func.count(Receipt.id))).scalar_one()
    rows = (
        db.session.execute(
            select(Receipt)
            .order_by(Receipt.created_at.desc())
            .limit(PAGE_SIZE)
            .offset((page - 1) * PAGE_SIZE)
        )
        .scalars()
        .all()
    )

    return render_template(
        "admin/receipts.html", receipts=rows, page=page, page_size=PAGE_SIZE, total=total
    )


@bp.route("/export/<string:dataset>.csv")
@admin_required
def export(dataset: str):
    """Export users or receipts.

    Columns are emitted from the same list that builds the header, so the two
    cannot drift apart the way they did in the previous export - which
    promised receipt fields and wrote row ids, user ids and kWh values.
    """
    if dataset == "users":
        columns = ["id", "username", "email", "is_admin", "is_active", "created_at", "last_login_at"]
        rows = db.session.execute(select(User).order_by(User.id)).scalars().all()

        def to_row(user: User) -> list:
            return [
                user.public_id,
                user.username,
                user.email,
                user.is_admin,
                user.is_active,
                user.created_at.isoformat() if user.created_at else "",
                user.last_login_at.isoformat() if user.last_login_at else "",
            ]

    elif dataset == "receipts":
        columns = [
            "receipt_id",
            "user_id",
            "created_at",
            "model",
            "region",
            "tokens_before",
            "tokens_after",
            "tokens_saved",
            "co2_g_saved",
            "retention_score",
        ]
        rows = db.session.execute(select(Receipt).order_by(Receipt.id)).scalars().all()

        def to_row(receipt: Receipt) -> list:
            return [
                receipt.receipt_id,
                receipt.user.public_id if receipt.user else "",
                receipt.created_at.isoformat() if receipt.created_at else "",
                receipt.model or "",
                receipt.region or "",
                receipt.tokens_before,
                receipt.tokens_after,
                receipt.tokens_saved,
                f"{receipt.co2_g_saved:.10f}",
                "" if receipt.retention_score is None else f"{receipt.retention_score:.4f}",
            ]

    else:
        abort(404)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(to_row(row) for row in rows)

    logger.info("Admin exported dataset", extra={"admin_id": current_user.id, "dataset": dataset})

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=ecoai-{dataset}.csv"},
    )
