"""Financial statements collector (income statement & balance sheet)."""

import json
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import text
from vnstock import Vnstock

from stock_collector.collectors.base import BaseCollector
from stock_collector.config import AppConfig
from stock_collector.db.engine import get_engine, get_session
from stock_collector.db.models import (
    FinancialBalanceSheet,
    FinancialIncomeStatement,
    StockListing,
)

logger = logging.getLogger(__name__)


class FinancialCollector(BaseCollector):
    """Collect financial statements (income statement & balance sheet)."""

    collection_type = "financial"

    def __init__(self, config: AppConfig):
        super().__init__(config)
        self.batch_size = config.collection.batch_size

    def collect(self, **kwargs) -> int:
        """
        Collect financial data.

        kwargs:
            symbols: list[str] — specific symbols (optional, defaults to all)
            period: str — 'year' or 'quarter' (default: 'quarter')
        """
        symbols = kwargs.get("symbols")
        period = kwargs.get("period", "quarter")

        if not symbols:
            symbols = self._get_all_symbols()

        if not symbols:
            logger.warning("No symbols found. Run listing collector first.")
            return 0

        logger.info(f"Collecting financial data for {len(symbols)} symbols (period={period})")

        total_records = 0
        failed_symbols = []
        skipped_symbols = []

        for i, symbol in enumerate(symbols):
            try:
                records = self._collect_symbol(symbol, period)
                total_records += records
                self._rate_limit()

                if (i + 1) % 50 == 0:
                    logger.info(
                        f"Progress: {i + 1}/{len(symbols)} symbols | "
                        f"{total_records} records | {len(failed_symbols)} failed | "
                        f"{len(skipped_symbols)} skipped"
                    )

            except Exception as e:
                error_str = str(e)
                # Data format errors = skip, don't count as failure
                if "are in the [columns]" in error_str or "KeyError" in error_str:
                    skipped_symbols.append(symbol)
                    logger.debug(f"{symbol}: no financial data available (skipped)")
                else:
                    failed_symbols.append(symbol)
                    logger.error(f"Failed to collect financials for {symbol}: {e}")
                continue

        if failed_symbols:
            logger.warning(f"Failed symbols ({len(failed_symbols)}): {failed_symbols[:20]}")
        if skipped_symbols:
            logger.info(f"Skipped {len(skipped_symbols)} symbols (no data available)")

        return total_records

    def _collect_symbol(self, symbol: str, period: str) -> int:
        """Collect income statement and balance sheet for one symbol."""
        records = 0

        try:
            stock = Vnstock().stock(symbol=symbol, source="VCI")
        except Exception as e:
            logger.error(f"{symbol}: failed to initialize stock object: {e}")
            return 0

        if stock.finance is None:
            logger.debug(f"{symbol}: finance module not available")
            return 0

        # Income Statement — no retry for data format errors
        try:
            finance = stock.finance
            income_df = finance.income_statement(period=period, lang="vi")
            if income_df is not None and not income_df.empty:
                r = self._save_income_statement(symbol, period, income_df)
                records += r
                logger.debug(f"{symbol}: saved {r} income statement records")
        except Exception as e:
            if "are in the [columns]" in str(e) or "KeyError" in str(e):
                logger.debug(f"{symbol}: income statement data not available")
            else:
                logger.warning(f"{symbol}: income statement error: {e}")

        self._rate_limit()

        # Balance Sheet — no retry for data format errors
        try:
            finance = stock.finance
            balance_df = finance.balance_sheet(period=period, lang="vi")
            if balance_df is not None and not balance_df.empty:
                r = self._save_balance_sheet(symbol, period, balance_df)
                records += r
                logger.debug(f"{symbol}: saved {r} balance sheet records")
        except Exception as e:
            if "are in the [columns]" in str(e) or "KeyError" in str(e):
                logger.debug(f"{symbol}: balance sheet data not available")
            else:
                logger.warning(f"{symbol}: balance sheet error: {e}")

        return records

    def _save_income_statement(self, symbol: str, period: str, df: pd.DataFrame) -> int:
        """Save income statement data with ON CONFLICT DO NOTHING."""
        records = 0
        engine = get_engine()

        insert_sql = text("""
            INSERT INTO financial_income_statements
                (symbol, period, year, quarter, revenue, year_revenue_growth,
                 cost_of_good_sold, gross_profit, operation_profit, net_income, raw_data)
            VALUES
                (:symbol, :period, :year, :quarter, :revenue, :year_revenue_growth,
                 :cost_of_good_sold, :gross_profit, :operation_profit, :net_income, :raw_data)
            ON CONFLICT (symbol, period, year, quarter) DO NOTHING
        """)

        with engine.begin() as conn:
            for _, row in df.iterrows():
                try:
                    year_raw = row.get("year", row.get("Year", 0))
                    year_val = int(year_raw) if year_raw is not None else 0
                    quarter_raw = row.get("quarter", row.get("Quarter"))
                    if quarter_raw is not None and bool(pd.notna(quarter_raw)):
                        quarter_val = int(quarter_raw)
                    else:
                        quarter_val = 0  # Use 0 for annual (NOT NULL in unique constraint)

                    # Build raw_data JSON from all columns
                    raw = {}
                    for col in df.columns:
                        val = row[col]
                        if val is not None and bool(pd.notna(val)):
                            raw[col] = val if not hasattr(val, 'item') else val.item()

                    conn.execute(
                        insert_sql,
                        {
                            "symbol": symbol,
                            "period": period,
                            "year": year_val,
                            "quarter": quarter_val,
                            "revenue": self._safe_numeric(row, ["revenue", "Revenue", "Doanh thu thuần"]),
                            "year_revenue_growth": self._safe_numeric(
                                row, ["yearRevenueGrowth", "year_revenue_growth"]
                            ),
                            "cost_of_good_sold": self._safe_numeric(
                                row, ["costOfGoodSold", "cost_of_good_sold", "Giá vốn hàng bán"]
                            ),
                            "gross_profit": self._safe_numeric(
                                row, ["grossProfit", "gross_profit", "Lợi nhuận gộp"]
                            ),
                            "operation_profit": self._safe_numeric(
                                row, ["operationProfit", "operation_profit"]
                            ),
                            "net_income": self._safe_numeric(
                                row, ["postTaxProfit", "net_income", "netIncome", "Lợi nhuận sau thuế"]
                            ),
                            "raw_data": json.dumps(raw, default=str, ensure_ascii=False),
                        },
                    )
                    records += 1
                except Exception as e:
                    logger.debug(f"Income insert error {symbol}: {e}")

        return records

    def _save_balance_sheet(self, symbol: str, period: str, df: pd.DataFrame) -> int:
        """Save balance sheet data with ON CONFLICT DO NOTHING."""
        records = 0
        engine = get_engine()

        insert_sql = text("""
            INSERT INTO financial_balance_sheets
                (symbol, period, year, quarter, total_assets, total_liabilities, equity, raw_data)
            VALUES
                (:symbol, :period, :year, :quarter, :total_assets, :total_liabilities, :equity, :raw_data)
            ON CONFLICT (symbol, period, year, quarter) DO NOTHING
        """)

        with engine.begin() as conn:
            for _, row in df.iterrows():
                try:
                    year_raw = row.get("year", row.get("Year", 0))
                    year_val = int(year_raw) if year_raw is not None else 0
                    quarter_raw = row.get("quarter", row.get("Quarter"))
                    if quarter_raw is not None and bool(pd.notna(quarter_raw)):
                        quarter_val = int(quarter_raw)
                    else:
                        quarter_val = 0

                    raw = {}
                    for col in df.columns:
                        val = row[col]
                        if val is not None and bool(pd.notna(val)):
                            raw[col] = val if not hasattr(val, 'item') else val.item()

                    conn.execute(
                        insert_sql,
                        {
                            "symbol": symbol,
                            "period": period,
                            "year": year_val,
                            "quarter": quarter_val,
                            "total_assets": self._safe_numeric(
                                row, ["asset", "totalAssets", "total_assets", "Tổng tài sản"]
                            ),
                            "total_liabilities": self._safe_numeric(
                                row, ["debt", "totalLiabilities", "total_liabilities", "Tổng nợ"]
                            ),
                            "equity": self._safe_numeric(
                                row, ["equity", "Equity", "Vốn chủ sở hữu"]
                            ),
                            "raw_data": json.dumps(raw, default=str, ensure_ascii=False),
                        },
                    )
                    records += 1
                except Exception as e:
                    logger.debug(f"Balance insert error {symbol}: {e}")

        return records

    @staticmethod
    def _safe_numeric(row, keys: list) -> float | None:
        """Safely extract a numeric value from a DataFrame row by trying multiple key names."""
        for key in keys:
            val = row.get(key)
            if val is not None and pd.notna(val):
                try:
                    return float(val)
                except (ValueError, TypeError):
                    continue
        return None

    def _get_all_symbols(self) -> list[str]:
        """Get all active symbols."""
        with get_session() as session:
            results = (
                session.query(StockListing.symbol)
                .filter(StockListing.status == "listed")
                .all()
            )
            return [r[0] for r in results]
