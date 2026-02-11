"""Base collector with shared logic: retry, rate limiting, logging."""

import logging
import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime

from stock_collector.config import AppConfig
from stock_collector.db.engine import get_session
from stock_collector.db.models import CollectionLog

logger = logging.getLogger(__name__)

# Errors that should NOT be retried (data format issues, not transient)
NON_RETRYABLE_KEYWORDS = [
    "are in the [columns]",
    "KeyError",
    "No data",
    "not found",
    "invalid symbol",
    "not supported",
    "NoneType",
]

# Errors that indicate rate limiting — should wait longer before retry
RATE_LIMIT_KEYWORDS = [
    "rate limit",
    "Rate Limit",
    "429",
    "too many requests",
    "Too Many Requests",
    "tối đa",
]


def _is_retryable(error: Exception) -> bool:
    """Check if an error is worth retrying (network/rate-limit) vs permanent (data format)."""
    error_str = str(error)
    for keyword in NON_RETRYABLE_KEYWORDS:
        if keyword in error_str:
            return False
    return True


def _is_rate_limited(error: Exception) -> bool:
    """Check if an error is specifically a rate limit error."""
    error_str = str(error)
    for keyword in RATE_LIMIT_KEYWORDS:
        if keyword in error_str:
            return True
    return False


class BaseCollector(ABC):
    """Abstract base class for all data collectors."""

    collection_type: str = "base"

    def __init__(self, config: AppConfig):
        self.config = config
        self.request_delay = config.collection.request_delay
        self.max_retries = config.collection.max_retries
        self.retry_delay = config.collection.retry_delay
        self.rate_limit_delay = getattr(config.collection, 'rate_limit_delay', 60)

    @abstractmethod
    def collect(self, **kwargs) -> int:
        """Run the collection. Returns number of records collected."""
        pass

    def run(self, **kwargs) -> int:
        """Execute collection with logging to DB."""
        log_entry = CollectionLog(
            collection_type=self.collection_type,
            symbol=kwargs.get("symbol"),
            status="running",
            started_at=datetime.utcnow(),
        )

        with get_session() as session:
            session.add(log_entry)
            session.flush()
            log_id = log_entry.id

        try:
            records = self.collect(**kwargs)

            with get_session() as session:
                log = session.get(CollectionLog, log_id)
                if log:
                    log.status = "success"  # type: ignore[assignment]
                    log.records_count = records  # type: ignore[assignment]
                    log.finished_at = datetime.utcnow()  # type: ignore[assignment]

            logger.info(
                f"[{self.collection_type}] Completed: {records} records"
                + (f" for {kwargs.get('symbol', '')}" if kwargs.get("symbol") else "")
            )
            return records

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            with get_session() as session:
                log = session.get(CollectionLog, log_id)
                if log:
                    log.status = "failed"  # type: ignore[assignment]
                    log.finished_at = datetime.utcnow()  # type: ignore[assignment]
                    log.error_message = error_msg[:2000]  # type: ignore[assignment]

            logger.error(f"[{self.collection_type}] Failed: {e}")
            raise

    def _rate_limit(self):
        """Sleep to respect rate limits."""
        time.sleep(self.request_delay)

    def _retry(self, func, *args, **kwargs):
        """Execute a function with smart retry logic.

        - Rate limit errors: wait longer (rate_limit_delay) then retry
        - Network/transient errors: normal retry with exponential backoff
        - Data format errors: fail immediately, no retry
        """
        last_exception: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                # Data format error — don't retry, it won't help
                if not _is_retryable(e):
                    logger.debug(
                        f"[{self.collection_type}] Non-retryable error (skipping): {e}"
                    )
                    raise

                # Rate limit error — wait much longer
                if _is_rate_limited(e):
                    wait = self.rate_limit_delay
                    logger.warning(
                        f"[{self.collection_type}] Rate limited! Waiting {wait}s before retry "
                        f"(attempt {attempt}/{self.max_retries})..."
                    )
                    time.sleep(wait)
                    continue

                # Normal transient error — exponential backoff
                if attempt < self.max_retries:
                    wait = self.retry_delay * attempt
                    logger.warning(
                        f"[{self.collection_type}] Attempt {attempt}/{self.max_retries} failed: {e}. "
                        f"Retrying in {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"[{self.collection_type}] All {self.max_retries} attempts failed."
                    )
        if last_exception is not None:
            raise last_exception
        raise RuntimeError(f"[{self.collection_type}] Retry logic exhausted with no exception recorded.")
