import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def _normalize_database_url(url: str) -> str:
    """
    Railway provides DATABASE_URL. SQLAlchemy expects a dialect.
    psycopg uses `postgresql+psycopg://`.
    """
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = _normalize_database_url(os.getenv("DATABASE_URL", ""))
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    # Railway runs a long-lived service; a small pool is fine.
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
    )

