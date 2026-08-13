"""Error handlers.

API routes get JSON, everything else gets a rendered page. The distinction is
made on the request path rather than on ``Accept``, because a browser fetching
``/api/...`` still sends ``Accept: */*``.
"""

from __future__ import annotations

import logging

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from ecoai.extensions import db

logger = logging.getLogger(__name__)


def _wants_json() -> bool:
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(400)
    def bad_request(error):
        return _respond(400, "bad_request", getattr(error, "description", "Malformed request."))

    @app.errorhandler(401)
    def unauthorized(error):
        return _respond(401, "authentication_required", "Sign in to continue.")

    @app.errorhandler(403)
    def forbidden(error):
        return _respond(403, "forbidden", "You do not have access to that.")

    @app.errorhandler(404)
    def not_found(error):
        return _respond(404, "not_found", "That page does not exist.")

    @app.errorhandler(413)
    def payload_too_large(error):
        return _respond(413, "payload_too_large", "That request body is too large.")

    @app.errorhandler(429)
    def rate_limited(error):
        description = getattr(error, "description", "Too many requests.")
        return _respond(429, "rate_limited", f"Too many requests. {description}")

    @app.errorhandler(500)
    def internal_error(error):
        # A failed request must not leave a poisoned session for the next one
        # to inherit from the connection pool.
        db.session.rollback()
        logger.exception("Unhandled error", extra={"path": request.path})
        return _respond(500, "internal_error", "Something went wrong on our side.")

    @app.errorhandler(Exception)
    def unexpected(error):
        if isinstance(error, HTTPException):
            return error
        db.session.rollback()
        logger.exception("Unhandled exception", extra={"path": request.path})
        return _respond(500, "internal_error", "Something went wrong on our side.")


def _respond(status: int, code: str, message: str):
    if _wants_json():
        return jsonify({"error": code, "message": message}), status
    return render_template("errors/error.html", status=status, message=message), status
