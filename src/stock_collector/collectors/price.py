"""Daily price (OHLCV) collector with incremental logic."""

import logging
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import func, text
from vnstock import Vnstock

from stock_collector.collectors.base import BaseCollector
from stock_collector.config import AppConfig
from stock_collector.db.engine import get_engine, get_session
from stock_collector.db.models import DailyPrice, StockListing

logger = logging.getLogger(__name__)


class PriceCollector(BaseCollector):
    """Collect daily OHLCV price data with incremental support."""

    collection_type = "price"

    def __init__(self, config: AppConfig):
        super().__init__(config)
        self.batch_size = config.collection.batch_size

    def collect(self, **kwargs) -> int:
        """
        Collect price data.

        kwargs:
            symbols: list[str] — specific symbols to collect (optional, defaults to all)
            start_date: str — start date for backfill mode (YYYY-MM-DD)
            end_date: str — end date for backfill mode (YYYY-MM-DD)
            mode: str — 'backfill' or 'incremental' (default: 'incremental')
        """
        mode = kwargs.get("mode", "incremental")
        symbols = kwargs.get("symbols")
        start_date = kwargs.get("start_date", self.config.collection.default_start_date)
        end_date = kwargs.get("end_date", date.today().strftime("%Y-%m-%d"))

        # Get symbols list
        if not symbols:
            symbols = self._get_all_symbols()

        if not symbols:
            logger.warning("No symbols found. Run listing collector first.")
            return 0

        logger.info(f"Collecting prices for {len(symbols)} symbols (mode={mode})")

        total_records = 0
        failed_symbols = []

        # Process in batches
        for i in range(0, len(symbols), self.batch_size):
            batch = symbols[i : i + self.batch_size]
            batch_num = i // self.batch_size + 1
            total_batches = (len(symbols) + self.batch_size - 1) // self.batch_size
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} symbols)")

            for symbol in batch:
                try:
                    if mode == "incremental":
                        records = self._collect_incremental(symbol, end_date)
                    else:
                        records = self._collect_backfill(symbol, start_date, end_date)

                    total_records += records
                    self._rate_limit()

                except Exception as e:
                    logger.error(f"Failed to collect {symbol}: {e}")
                    failed_symbols.append(symbol)
                    continue

        if failed_symbols:
            logger.warning(f"Failed symbols ({len(failed_symbols)}): {failed_symbols[:20]}")

        return total_records

    def _collect_incremental(self, symbol: str, end_date: str) -> int:
        """Only fetch data from the last date in DB + 1 day to today."""
        last_date = self._get_last_date(symbol)

        if last_date:
            start = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
            if start > end_date:
                logger.debug(f"{symbol}: already up-to-date (last={last_date})")
                return 0
        else:
            # No data yet — backfill from default start
            start = self.config.collection.default_start_date

        logger.info(f"{symbol}: incremental collect from {start} to {end_date}")
        return self._fetch_and_save(symbol, start, end_date)

    def _collect_backfill(self, symbol: str, start_date: str, end_date: str) -> int:
        """Fetch full range of data."""
        logger.info(f"{symbol}: backfill from {start_date} to {end_date}")
        return self._fetch_and_save(symbol, start_date, end_date)

    def _fetch_and_save(self, symbol: str, start_date: str, end_date: str) -> int:
        """Fetch data from vnstock API and save to DB."""
        try:
            stock = Vnstock().stock(symbol=symbol, source="VCI")
            df = self._retry(
                stock.quote.history,
                start=start_date,
                end=end_date,
                interval="1D",
            )
        except Exception as e:
            logger.error(f"API error for {symbol}: {e}")
            return 0

        if df is None or df.empty:
            logger.debug(f"{symbol}: no data returned for {start_date} to {end_date}")
            return 0

        # Normalize column names
        col_map = {
            "time": "trading_date",
            "date": "trading_date",
            "TradingDate": "trading_date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        if "trading_date" not in df.columns:
            logger.warning(f"{symbol}: 'trading_date' column not found. Columns: {list(df.columns)}")
            return 0

        # Ensure trading_date is proper date
        df["trading_date"] = pd.to_datetime(df["trading_date"]).dt.date

        # Insert with ON CONFLICT DO NOTHING
        records = 0
        engine = get_engine()
        insert_sql = text("""
            INSERT INTO daily_prices (symbol, trading_date, open, high, low, close, volume)
            VALUES (:symbol, :trading_date, :open, :high, :low, :close, :volume)
            ON CONFLICT (symbol, trading_date) DO NOTHING
        """)

        with engine.begin() as conn:
            for _, row in df.iterrows():
                try:
                    conn.execute(
                        insert_sql,
                        {
                            "symbol": symbol,
                            "trading_date": row["trading_date"],
                            "open": float(row.get("open", 0)) if pd.notna(row.get("open")) else None,
                            "high": float(row.get("high", 0)) if pd.notna(row.get("high")) else None,
                            "low": float(row.get("low", 0)) if pd.notna(row.get("low")) else None,
                            "close": float(row.get("close", 0)) if pd.notna(row.get("close")) else None,
                            "volume": int(row.get("volume", 0)) if pd.notna(row.get("volume")) else None,
                        },
                    )
                    records += 1
                except Exception as e:
                    logger.debug(f"Insert error for {symbol} {row.get('trading_date')}: {e}")

        return records

    def _get_last_date(self, symbol: str) -> date | None:
        """Get the most recent trading_date for a symbol in DB."""
        with get_session() as session:
            result = (
                session.query(func.max(DailyPrice.trading_date))
                .filter(DailyPrice.symbol == symbol)
                .scalar()
            )
            return result

    def _get_all_symbols(self) -> list[str]:
        """Get all active symbols from the stock_listings table."""
        with get_session() as session:
            results = (
                session.query(StockListing.symbol)
                .filter(StockListing.status == "listed")
                .all()
            )
            return [r[0] for r in results]
