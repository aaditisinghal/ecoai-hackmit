"""WSGI entrypoint.

Production servers import the module level ``app`` object:

    gunicorn wsgi:app

Running this file directly starts the Flask development server, which is
convenient locally but must never be used to serve real traffic.
"""

from __future__ import annotations

from ecoai import create_app

app = create_app()


if __name__ == "__main__":
    app.run(
        host=app.config["DEV_SERVER_HOST"],
        port=app.config["PORT"],
        debug=app.config["DEBUG"],
    )
