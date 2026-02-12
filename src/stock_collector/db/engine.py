"""SQLAlchemy engine and session management."""

import atexit
import logging
import threading
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from stock_collector.config import AppConfig

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None
_lock = threading.Lock()


def init_engine(config: AppConfig) -> None:
    """
    Initialize the SQLAlchemy engine and session factory.
    
    This function is thread-safe and idempotent. It configures:
    - Connection pooling with IPv4 preference
    - Connection timeout (10 seconds)
    - Pool recycle for long-lived connections
    - Pre-ping to detect stale connections
    
    Args:
        config: Application configuration containing database settings
        
    Raises:
        ValueError: If database configuration is invalid
    """
    global _engine, _SessionLocal
    
    if _engine is not None:
        logger.debug("Database engine already initialized, skipping re-initialization")
        return
    
    with _lock:
        # Double-check after acquiring lock
        if _engine is not None:
            return
        
        try:
            # Build database URL with connection arguments for IPv4 preference
            db_url = config.db.url
            
            # PostgreSQL-specific connect_args for better connection handling
            connect_args = {
                "connect_timeout": 10,  # 10 second connection timeout
                "options": "-c statement_timeout=300000",  # 5 minute statement timeout
            }
            
            # Try to force IPv4 connection
            try:
                import socket
                addr_info = socket.getaddrinfo(config.db.host, config.db.port, family=socket.AF_INET)
                if addr_info:
                    ipv4_addr = str(addr_info[0][4][0])
                    logger.info(f"Resolved {config.db.host} to IPv4: {ipv4_addr}")
                    db_url = db_url.replace(config.db.host, ipv4_addr)
            except Exception as e:
                logger.warning(f"IPv4 resolution failed for {config.db.host}, using default: {e}")
            
            _engine = create_engine(
                db_url,
                pool_size=5,
                max_overflow=10,
                pool_recycle=3600,  # Recycle connections after 1 hour
                pool_pre_ping=True,  # Test connections before using them
                connect_args=connect_args,
                echo=False,
                future=True,
            )
            
            # Register event listener for connection pool
            @event.listens_for(_engine, "engine_disposed")
            def receive_engine_disposed(engine):
                logger.debug("Engine connection pool disposed")
            
            _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
            
            # Register cleanup on exit
            atexit.register(dispose_engine)
            
            logger.info(
                f"Database engine initialized: {config.db.host}:{config.db.port}/{config.db.name}"
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize database engine: {e}", exc_info=True)
            _engine = None
            raise




def get_engine() -> Engine:
    """
    Get the current SQLAlchemy engine.
    
    Returns:
        Engine: The initialized SQLAlchemy engine
        
    Raises:
        RuntimeError: If engine is not initialized
    """
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_engine() first.")
    return _engine


def dispose_engine() -> None:
    """Dispose of the engine and clean up connections."""
    global _engine
    if _engine is not None:
        try:
            _engine.dispose()
            logger.info("Database engine disposed successfully")
        except Exception as e:
            logger.error(f"Error disposing database engine: {e}", exc_info=True)
        finally:
            _engine = None


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Get a database session as a context manager.
    
    Usage:
        with get_session() as session:
            # Use session
            result = session.query(...).all()
    
    Yields:
        Session: SQLAlchemy database session
        
    Raises:
        RuntimeError: If engine is not initialized
    """
    if _SessionLocal is None:
        raise RuntimeError("Database engine not initialized. Call init_engine() first.")
    
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Session error, rolling back: {e}", exc_info=True)
        raise
    finally:
        session.close()




def create_all_tables() -> None:
    """
    Create all tables defined in the ORM models.
    
    This is idempotent - it only creates tables that don't exist.
    
    Raises:
        RuntimeError: If engine is not initialized
    """
    try:
        from stock_collector.db.models import Base
        engine = get_engine()
        Base.metadata.create_all(engine)
        logger.info("All database tables created successfully")
    except RuntimeError as e:
        logger.error(f"Cannot create tables: {e}")
        raise
    except Exception as e:
        logger.error(f"Error creating tables: {e}", exc_info=True)
        raise


def test_connection() -> bool:
    """
    Test the database connection.
    
    Returns:
        bool: True if connection is successful, False otherwise
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection test: OK")
        return True
    except RuntimeError as e:
        logger.error(f"Database not initialized: {e}")
        return False
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False
