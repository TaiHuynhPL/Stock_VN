"""Stock listing collector - fetches all listed symbols."""

import logging
from datetime import datetime

import pandas as pd
from vnstock import Vnstock

from stock_collector.collectors.base import BaseCollector
from stock_collector.config import AppConfig
from stock_collector.db.engine import get_session
from stock_collector.db.models import StockListing

logger = logging.getLogger(__name__)


class ListingCollector(BaseCollector):
    """Collect and update the list of all stock symbols."""

    collection_type = "listing"

    def __init__(self, config: AppConfig):
        super().__init__(config)

    def collect(self, **kwargs) -> int:
        """Fetch all stock symbols and upsert into DB."""
        logger.info("Fetching all stock symbols...")

        # vnstock requires a symbol to create stock object, use any valid one
        stock = Vnstock().stock(symbol="VNM", source="VCI")
        df = self._retry(stock.listing.all_symbols)

        if df is None or df.empty:
            logger.warning("No stock symbols returned from API.")
            return 0

        logger.info(f"Fetched {len(df)} symbols from API. Columns: {list(df.columns)}")

        count = 0
        with get_session() as session:
            for _, row in df.iterrows():
                symbol = str(row.get("symbol", row.get("ticker", ""))).strip().upper()
                if not symbol:
                    continue

                organ_name = row.get("organ_name", row.get("organName"))

                existing = session.get(StockListing, symbol)
                if existing:
                    # Update existing record
                    if organ_name:
                        existing.organ_name = organ_name
                    existing.updated_at = datetime.utcnow()  # type: ignore[assignment]
                else:
                    # Insert new record
                    listing = StockListing(
                        symbol=symbol,
                        organ_name=organ_name,
                        status="listed",
                    )
                    session.add(listing)

                count += 1

        logger.info(f"Upserted {count} stock listings.")
        return count
