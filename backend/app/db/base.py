# Import all models for Alembic autodetect
from app.db.session import Base  # noqa
from app.models.user import User  # noqa
from app.models.trade import Account, Trade  # noqa
