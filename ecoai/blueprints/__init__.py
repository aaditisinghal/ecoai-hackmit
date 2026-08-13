"""HTTP layer.

One blueprint per concern, each mounted by :func:`ecoai.create_app`. The
previous application defined all 27 routes in a single 1,238 line module.
"""

from ecoai.blueprints import admin, api, auth, dashboard, oauth, public, studio

__all__ = ["admin", "api", "auth", "dashboard", "oauth", "public", "studio"]
