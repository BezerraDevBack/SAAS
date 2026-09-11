# IP — Caramurú Construções — assinatura do autor

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import settings


def alembic_sync_url() -> str:
    """Alembic usa driver síncrono (psycopg / postgresql) sobre a mesma URL async."""
    return settings.database_url.replace("postgresql+asyncpg", "postgresql+psycopg")


def get_sync_engine() -> Engine:
    return create_engine(alembic_sync_url(), pool_pre_ping=True)
