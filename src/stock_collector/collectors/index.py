"""Market index collector (VNINDEX, HNX-INDEX, UPCOM-INDEX)."""

import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import func, text
from vnstock import Vnstock

from stock_collector.collectors.base import BaseCollector
from stock_collector.config import AppConfig
from stock_collector.db.engine import get_engine, get_session
from stock_collector.db.models import MarketIndex

logger = logging.getLogger(__name__)


class IndexCollector(BaseCollector):
    """Collect market index data with incremental support."""

    collection_type = "index"

    def __init__(self, config: AppConfig):
        super().__init__(config)

    def collect(self, **kwargs) -> int:
        """
        Collect market index data.

        kwargs:
            indices: list[str] — index names (default from config)
            start_date: str — for backfill
            end_date: str — for backfill
            mode: str — 'backfill' or 'incremental'
        """
        mode = kwargs.get("mode", "incremental")
        indices = kwargs.get("indices", self.config.indices)
        start_date = kwargs.get("start_date", self.config.collection.default_start_date)
        end_date = kwargs.get("end_date", date.today().strftime("%Y-%m-%d"))

        total_records = 0

        for index_name in indices:
            try:
                if mode == "incremental":
                    records = self._collect_incremental(index_name, end_date)
                else:
                    records = self._collect_backfill(index_name, start_date, end_date)
                total_records += records
                self._rate_limit()
            except Exception as e:
                logger.error(f"Failed to collect index {index_name}: {e}")

        return total_records

    def _collect_incremental(self, index_name: str, end_date: str) -> int:
        """Incremental: only fetch from last date in DB."""
        last_date = self._get_last_date(index_name)

        if last_date:
            start = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
            if start > end_date:
                logger.debug(f"{index_name}: already up-to-date (last={last_date})")
                return 0
        else:
            start = self.config.collection.default_start_date

        logger.info(f"{index_name}: incremental from {start} to {end_date}")
        return self._fetch_and_save(index_name, start, end_date)

    def _collect_backfill(self, index_name: str, start_date: str, end_date: str) -> int:
        """Backfill full range."""
        logger.info(f"{index_name}: backfill from {start_date} to {end_date}")
        return self._fetch_and_save(index_name, start_date, end_date)

    def _fetch_and_save(self, index_name: str, start_date: str, end_date: str) -> int:
        """Fetch index data from vnstock and save to DB."""
        try:
            stock = Vnstock().stock(symbol=index_name, source="VCI")
            df = self._retry(
                stock.quote.history,
                start=start_date,
                end=end_date,
                interval="1D",
            )
        except Exception as e:
            logger.error(f"API error for index {index_name}: {e}")
            return 0

        if df is None or df.empty:
            logger.debug(f"{index_name}: no data returned")
            return 0

        # Normalize columns
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
            logger.warning(f"{index_name}: 'trading_date' column not found. Columns: {list(df.columns)}")
            return 0

        df["trading_date"] = pd.to_datetime(df["trading_date"]).dt.date

        records = 0
        engine = get_engine()
        insert_sql = text("""
            INSERT INTO market_indices (index_name, trading_date, open, high, low, close, volume)
            VALUES (:index_name, :trading_date, :open, :high, :low, :close, :volume)
            ON CONFLICT (index_name, trading_date) DO NOTHING
        """)

        with engine.begin() as conn:
            for _, row in df.iterrows():
                try:
                    conn.execute(
                        insert_sql,
                        {
                            "index_name": index_name,
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
                    logger.debug(f"Index insert error {index_name}: {e}")

        logger.info(f"{index_name}: saved {records} records")
        return records

    def _get_last_date(self, index_name: str) -> date | None:
        """Get the most recent trading_date for an index in DB."""
        with get_session() as session:
            result = (
                session.query(func.max(MarketIndex.trading_date))
                .filter(MarketIndex.index_name == index_name)
                .scalar()
            )
            return result
