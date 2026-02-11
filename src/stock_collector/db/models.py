"""SQLAlchemy ORM models for Vietnamese stock market data."""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class StockListing(Base):
    """Danh sách mã chứng khoán niêm yết."""

    __tablename__ = "stock_listings"

    symbol = Column(String(20), primary_key=True, comment="Mã CK (VNM, FPT...)")
    organ_name = Column(String(500), nullable=True, comment="Tên công ty")
    organ_short_name = Column(String(255), nullable=True, comment="Tên viết tắt")
    exchange = Column(String(10), nullable=True, comment="Sàn: HOSE/HNX/UPCOM")
    industry = Column(String(500), nullable=True, comment="Ngành")
    status = Column(String(20), default="listed", comment="Trạng thái: listed/delisted")
    first_listed_date = Column(Date, nullable=True, comment="Ngày niêm yết đầu tiên")
    created_at = Column(DateTime, default=datetime.utcnow, comment="Ngày tạo bản ghi")
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="Ngày cập nhật"
    )

    def __repr__(self):
        return f"<StockListing(symbol={self.symbol}, name={self.organ_short_name}, exchange={self.exchange})>"


class DailyPrice(Base):
    """Dữ liệu giá OHLCV hằng ngày - bảng chính cho phân tích kỹ thuật."""

    __tablename__ = "daily_prices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True, comment="Mã CK")
    trading_date = Column(Date, nullable=False, comment="Ngày giao dịch")
    open = Column(Numeric(15, 2), nullable=True, comment="Giá mở cửa")
    high = Column(Numeric(15, 2), nullable=True, comment="Giá cao nhất")
    low = Column(Numeric(15, 2), nullable=True, comment="Giá thấp nhất")
    close = Column(Numeric(15, 2), nullable=True, comment="Giá đóng cửa")
    volume = Column(BigInteger, nullable=True, comment="Khối lượng giao dịch")

    __table_args__ = (
        UniqueConstraint("symbol", "trading_date", name="uq_daily_prices_symbol_date"),
        Index("ix_daily_prices_trading_date", "trading_date"),
        Index("ix_daily_prices_symbol_date_desc", "symbol", trading_date.desc()),
    )

    def __repr__(self):
        return f"<DailyPrice(symbol={self.symbol}, date={self.trading_date}, close={self.close})>"


class FinancialIncomeStatement(Base):
    """Báo cáo kết quả kinh doanh."""

    __tablename__ = "financial_income_statements"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True, comment="Mã CK")
    period = Column(String(10), nullable=False, comment="year/quarter")
    year = Column(Integer, nullable=False, comment="Năm")
    quarter = Column(Integer, nullable=True, comment="Quý (null cho annual)")
    revenue = Column(Numeric(20, 2), nullable=True, comment="Doanh thu thuần")
    year_revenue_growth = Column(Numeric(10, 4), nullable=True, comment="Tăng trưởng DT YoY")
    cost_of_good_sold = Column(Numeric(20, 2), nullable=True, comment="Giá vốn hàng bán")
    gross_profit = Column(Numeric(20, 2), nullable=True, comment="Lợi nhuận gộp")
    operation_profit = Column(Numeric(20, 2), nullable=True, comment="LN từ HĐKD")
    net_income = Column(Numeric(20, 2), nullable=True, comment="Lợi nhuận sau thuế")
    raw_data = Column(JSONB, nullable=True, comment="Dữ liệu gốc đầy đủ từ API")

    __table_args__ = (
        UniqueConstraint("symbol", "period", "year", "quarter", name="uq_income_stmt"),
        Index("ix_income_stmt_symbol_year", "symbol", "year"),
    )

    def __repr__(self):
        return f"<IncomeStatement(symbol={self.symbol}, {self.period} {self.year} Q{self.quarter})>"


class FinancialBalanceSheet(Base):
    """Bảng cân đối kế toán."""

    __tablename__ = "financial_balance_sheets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True, comment="Mã CK")
    period = Column(String(10), nullable=False, comment="year/quarter")
    year = Column(Integer, nullable=False, comment="Năm")
    quarter = Column(Integer, nullable=True, comment="Quý (null cho annual)")
    total_assets = Column(Numeric(20, 2), nullable=True, comment="Tổng tài sản")
    total_liabilities = Column(Numeric(20, 2), nullable=True, comment="Tổng nợ phải trả")
    equity = Column(Numeric(20, 2), nullable=True, comment="Vốn chủ sở hữu")
    raw_data = Column(JSONB, nullable=True, comment="Dữ liệu gốc đầy đủ từ API")

    __table_args__ = (
        UniqueConstraint("symbol", "period", "year", "quarter", name="uq_balance_sheet"),
        Index("ix_balance_sheet_symbol_year", "symbol", "year"),
    )

    def __repr__(self):
        return f"<BalanceSheet(symbol={self.symbol}, {self.period} {self.year} Q{self.quarter})>"


class MarketIndex(Base):
    """Dữ liệu chỉ số thị trường (VNINDEX, HNX-INDEX, UPCOM-INDEX)."""

    __tablename__ = "market_indices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    index_name = Column(String(30), nullable=False, comment="Tên chỉ số")
    trading_date = Column(Date, nullable=False, comment="Ngày giao dịch")
    open = Column(Numeric(15, 2), nullable=True, comment="Giá mở cửa")
    high = Column(Numeric(15, 2), nullable=True, comment="Giá cao nhất")
    low = Column(Numeric(15, 2), nullable=True, comment="Giá thấp nhất")
    close = Column(Numeric(15, 2), nullable=True, comment="Giá đóng cửa")
    volume = Column(BigInteger, nullable=True, comment="Khối lượng")

    __table_args__ = (
        UniqueConstraint("index_name", "trading_date", name="uq_market_index_date"),
        Index("ix_market_index_name_date", "index_name", "trading_date"),
    )

    def __repr__(self):
        return f"<MarketIndex(index={self.index_name}, date={self.trading_date}, close={self.close})>"


class CollectionLog(Base):
    """Log quá trình thu thập dữ liệu - dùng để theo dõi và debug."""

    __tablename__ = "collection_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    collection_type = Column(
        String(50), nullable=False, comment="Loại: listing/price/financial/index"
    )
    symbol = Column(String(20), nullable=True, comment="Mã CK (null cho listing/index)")
    status = Column(String(20), nullable=False, default="running", comment="running/success/failed")
    records_count = Column(Integer, nullable=True, default=0, comment="Số bản ghi thu thập")
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="Thời gian bắt đầu")
    finished_at = Column(DateTime, nullable=True, comment="Thời gian kết thúc")
    error_message = Column(Text, nullable=True, comment="Thông báo lỗi nếu failed")

    __table_args__ = (
        Index("ix_collection_logs_type_status", "collection_type", "status"),
        Index("ix_collection_logs_started", "started_at"),
    )

    def __repr__(self):
        return f"<CollectionLog(type={self.collection_type}, status={self.status}, records={self.records_count})>"
