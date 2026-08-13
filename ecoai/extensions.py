"""Flask extension singletons.

They are instantiated unbound here and attached to an application inside
:func:`ecoai.create_app`, so importing a model or a blueprint never triggers
application setup and tests can build as many isolated apps as they need.
"""

from __future__ import annotations

from authlib.integrations.flask_client import OAuth
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from ecoai.models.base import Base

db = SQLAlchemy(model_class=Base)
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()
oauth = OAuth()
limiter = Limiter(key_func=get_remote_address)
