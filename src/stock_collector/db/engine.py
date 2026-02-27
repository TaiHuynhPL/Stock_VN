"""SQLAlchemy engine and session management.

This module manages database connections for PostgreSQL. It includes:
- Thread-safe engine initialization with idempotent behavior
- Auto-detection of Supabase direct hosts and fallback to Connection Pooler
- IPv4 connection preference to avoid IPv6-only environments (GitHub Actions, Docker)
- Connection pooling with automatic health checks (pool_pre_ping)
- Exponential backoff retry logic for transient connection errors
- Automatic cleanup on application exit
- Connection timeout (10s) and statement timeout (5 min)

Supabase IPv6 Issue:
  Supabase direct connection hosts (db.<ref>.supabase.co) only have AAAA records
  (IPv6). Environments like GitHub Actions runners and some Docker setups don't
  support IPv6 outbound. This module automatically detects this and switches to
  the Supabase Connection Pooler (Supavisor) which has IPv4 A records.
"""

import atexit
import logging
import os
import re
import socket
import threading
import time
from contextlib import contextmanager
from typing import Generator, Optional
from urllib.parse import quote_plus

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from stock_collector.config import AppConfig

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None
_lock = threading.Lock()


def _resolve_ipv4(hostname: str, port: int) -> Optional[str]:
    """Try to resolve hostname to an IPv4 address. Returns None if not found."""
    try:
        # Strategy 1: AF_INET only
        addr_info = socket.getaddrinfo(hostname, port, family=socket.AF_INET)
        if addr_info:
            return str(addr_info[0][4][0])
    except socket.gaierror:
        pass

    try:
        # Strategy 2: AF_UNSPEC, filter for IPv4
        addr_info = socket.getaddrinfo(hostname, port, family=socket.AF_UNSPEC)
        ipv4_results = [a for a in addr_info if a[0] == socket.AF_INET]
        if ipv4_results:
            return str(ipv4_results[0][4][0])
    except socket.gaierror:
        pass

    return None


def _detect_supabase_region(project_ref: str) -> str:
    """Detect Supabase project region via health endpoint."""
    try:
        import urllib.request

        url = f"https://{project_ref}.supabase.co/auth/v1/health"
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "stock-collector/1.0")

        with urllib.request.urlopen(req, timeout=5) as resp:
            for header_name in ("sb-region", "x-region", "fly-region"):
                val = resp.headers.get(header_name, "")
                if val:
                    logger.info(f"  Detected Supabase region: {val}")
                    return val.strip()
    except Exception as e:
        logger.debug(f"  Could not auto-detect Supabase region: {e}")

    # Default for Vietnamese users (Singapore — closest region)
    return "ap-southeast-1"


def _get_supabase_pooler(host: str, user: str) -> Optional[tuple[str, int, str]]:
    """
    If host is a Supabase direct connection (db.<ref>.supabase.co),
    return (pooler_host, pooler_port, pooler_user) for session mode.
    Returns None if not a Supabase direct host.
    """
    match = re.match(r"^db\.([a-z0-9]+)\.supabase\.co$", host)
    if not match:
        return None

    project_ref = match.group(1)

    # Allow region override via env var
    region = os.environ.get("SUPABASE_REGION", "").strip()
    if not region:
        region = _detect_supabase_region(project_ref)

    pooler_host = f"aws-0-{region}.pooler.supabase.com"
    pooler_port = 6543   # Session mode (compatible with ORMs)
    pooler_user = f"postgres.{project_ref}"

    return (pooler_host, pooler_port, pooler_user)


def init_engine(config: AppConfig) -> None:
    """
    Initialize the SQLAlchemy engine and session factory.

    This function is thread-safe and idempotent. It configures:
    - Connection pooling with IPv4 preference
    - Auto Supabase pooler fallback when IPv4 is unavailable
    - Connection timeout (10 seconds)
    - Pool recycle for long-lived connections
    - Pre-ping to detect stale connections
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
            db_url = config.db.url
            ipv4_addr = None
            effective_host = config.db.host
            effective_port = config.db.port

            # --- Priority 1: Use DB_POOLER_URL if set (Supabase pooler) ---
            if config.db.pooler_url:
                db_url = config.db.pooler_url
                logger.info("🔄 Using DB_POOLER_URL (Supabase pooler connection)")

                # Try to extract host from pooler URL for IPv4 resolution
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(db_url)
                    if parsed.hostname:
                        effective_host = parsed.hostname
                        effective_port = parsed.port or 6543
                        ipv4_addr = _resolve_ipv4(effective_host, effective_port)
                        if ipv4_addr:
                            logger.info(f"  ✓ Pooler resolved to IPv4: {ipv4_addr}")
                except Exception:
                    pass

            # --- Priority 2: Standard host with IPv4 resolution ---
            elif config.db.host not in ("localhost", "127.0.0.1", "::1"):
                ipv4_addr = _resolve_ipv4(config.db.host, config.db.port)
                if ipv4_addr:
                    logger.info(f"✓ Resolved {config.db.host} to IPv4: {ipv4_addr}")
                    db_url = db_url.replace(config.db.host, ipv4_addr)
                else:
                    logger.warning(
                        f"⚠ No IPv4 for {config.db.host} — connection may fail.\n"
                        f"  Set DB_POOLER_URL env var with your Supabase pooler "
                        f"connection string (Dashboard → Settings → Database → Session mode)"
                    )
            else:
                logger.debug(f"Skipping DNS resolution for {config.db.host}")

            # --- Build connect_args ---
            connect_args = {
                "connect_timeout": 10,
                "options": "-c statement_timeout=300000",  # 5 min
                "application_name": "stock_collector",
                "tcp_user_timeout": 10000,
            }

            if ipv4_addr:
                connect_args["hostaddr"] = ipv4_addr
                logger.debug(f"Using hostaddr={ipv4_addr} to enforce IPv4")

            # --- Create engine ---
            _engine = create_engine(
                db_url,
                pool_size=5,
                max_overflow=10,
                pool_recycle=3600,
                pool_pre_ping=True,
                connect_args=connect_args,
                echo=False,
                future=True,
            )

            @event.listens_for(_engine, "engine_disposed")
            def receive_engine_disposed(engine):
                logger.debug("Engine connection pool disposed")

            _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

            atexit.register(dispose_engine)

            logger.info(
                f"Database engine initialized: "
                f"{effective_host}:{effective_port}/{config.db.name}"
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


def _test_connection_with_retry(max_retries: int = 3, backoff_factor: float = 2.0) -> bool:
    """
    Test database connection with exponential backoff retry.
    
    Args:
        max_retries: Maximum number of retry attempts
        backoff_factor: Exponential backoff multiplier
        
    Returns:
        bool: True if connection successful, False otherwise
    """
    engine = get_engine()
    
    for attempt in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.debug(f"Database connection test successful on attempt {attempt + 1}")
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = backoff_factor ** attempt
                logger.warning(
                    f"Connection attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
            else:
                logger.error(f"Connection failed after {max_retries} attempts: {e}")
                return False
    
    return False


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
    Get a database session as a context manager with automatic IPv6 error recovery.
    
    This context manager implements automatic retry logic when IPv6 connection
    errors are detected. If a connection fails due to IPv6 being unreachable:
    1. Detects IPv6-related errors (pattern matching)
    2. Disposes connection pool to force fresh connection
    3. Retries with exponential backoff (1s, 2s, 4s)
    4. Gradually increases timeouts to help recovery
    
    Usage:
        with get_session() as session:
            result = session.query(...).all()
    
    Yields:
        Session: SQLAlchemy database session
        
    Raises:
        RuntimeError: If engine is not initialized
        sqlalchemy.exc.OperationalError: If all retries exhausted
    """
    if _SessionLocal is None:
        raise RuntimeError("Database engine not initialized. Call init_engine() first.")
    
    max_retries = 4
    retry_count = 0
    ipv6_error_detected = False
    
    while retry_count <= max_retries:
        session = _SessionLocal()
        try:
            yield session
            session.commit()
            if retry_count > 0:
                logger.info(f"✓ Connection recovered after {retry_count} retries")
            return
            
        except Exception as e:
            session.rollback()
            
            # Detect IPv6-related connection errors
            error_str = str(e).lower()
            error_full = str(e)
            
            is_ipv6_error = (
                "2406:" in error_full  # IPv6 address pattern
                or "network is unreachable" in error_str
                or "no route to host" in error_str
                or "connection refused" in error_str and retry_count < max_retries
                or "timeout" in error_str and retry_count < max_retries
            )
            
            if is_ipv6_error and retry_count < max_retries:
                ipv6_error_detected = True
                retry_count += 1
                wait_time = 2 ** (retry_count - 1)  # 1s, 2s, 4s, 8s
                
                logger.warning(
                    f"🔄 Connection error detected (attempt {retry_count}/{max_retries}): "
                    f"{error_str[:80]}... Retrying in {wait_time}s..."
                )
                
                # Dispose pool to force new connection with fresh DNS resolution
                engine = get_engine()
                engine.dispose()
                logger.debug(f"  → Disposed connection pool")
                
                time.sleep(wait_time)
                continue
            else:
                # Not a retriable error or max retries exceeded
                if ipv6_error_detected:
                    logger.error(
                        f"✗ Connection failed after {retry_count} retries. "
                        f"Last error: {error_str[:100]}",
                        exc_info=True
                    )
                else:
                    logger.error(f"✗ Session error (non-retriable): {error_str[:100]}", exc_info=True)
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
    Test the database connection with retry logic.
    
    Returns:
        bool: True if connection is successful, False otherwise
    """
    try:
        return _test_connection_with_retry(max_retries=3, backoff_factor=2.0)
    except RuntimeError as e:
        logger.error(f"Database not initialized: {e}")
        return False
