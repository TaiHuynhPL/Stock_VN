"""SQLAlchemy engine and session management."""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from stock_collector.config import AppConfig

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def init_engine(config: AppConfig):
    """Initialize the SQLAlchemy engine and session factory."""
    global _engine, _SessionLocal
    _engine = create_engine(
        config.db.url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=False,
    )
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    logger.info(f"Database engine initialized: {config.db.host}:{config.db.port}/{config.db.name}")


def get_engine():
    """Get the current SQLAlchemy engine."""
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_engine() first.")
    return _engine


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get a database session as a context manager."""
    if _SessionLocal is None:
        raise RuntimeError("Database engine not initialized. Call init_engine() first.")
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all_tables():
    """Create all tables defined in the ORM models."""
    from stock_collector.db.models import Base
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("All database tables created successfully.")


def test_connection() -> bool:
    """Test the database connection."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection test: OK")
        return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False
