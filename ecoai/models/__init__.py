"""SQLAlchemy models.

Importing this package registers every model on the shared metadata, which is
what Alembic autogeneration walks to detect schema changes.
"""

from ecoai.models.base import Base, TimestampMixin, utcnow
from ecoai.models.ml import MlLearningEvent, MlPerformanceSnapshot
from ecoai.models.receipt import Receipt
from ecoai.models.user import User

__all__ = [
    "Base",
    "MlLearningEvent",
    "MlPerformanceSnapshot",
    "Receipt",
    "TimestampMixin",
    "User",
    "utcnow",
]
