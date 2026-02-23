# Vietnamese Stock Market Data Collector 🇻🇳

Ứng dụng Python tự động thu thập dữ liệu chứng khoán Việt Nam và lưu vào PostgreSQL.

## Tính năng

- 📋 Thu thập danh sách tất cả mã chứng khoán (HOSE, HNX, UPCOM)
- 📈 Thu thập dữ liệu giá OHLCV hằng ngày cho tất cả mã CK
- 📊 Thu thập dữ liệu chỉ số thị trường (VNINDEX, HNX-INDEX, UPCOM-INDEX)
- 💰 Thu thập báo cáo tài chính (BCTC, CĐKT)
- 🔄 Incremental collection — chỉ thu thập dữ liệu mới, không lặp lại
- 🐳 Docker support cho deployment

## Cài đặt Local

### 1. Yêu cầu
- Python 3.10+
- PostgreSQL 14+

### 2. Cài đặt dependencies

```bash
cd Stock_VN
pip install -e .
```

### 3. Cấu hình

```bash
cp .env.example .env
# Sửa .env với thông tin PostgreSQL của bạn
```

### 4. Khởi tạo database

```bash
stock-collector init-db
```

## Sử dụng

### Backfill — Thu thập toàn bộ dữ liệu lịch sử

```bash
# Thu thập tất cả (listing + price + index + financial)
stock-collector backfill --start 2005-01-01

# Chỉ thu thập giá cho một số mã cụ thể
stock-collector backfill --symbols VNM,FPT,VIC --start 2005-01-01

# Chỉ thu thập chỉ số thị trường
stock-collector backfill --type index --start 2005-01-01
```

### Collect Daily — Thu thập dữ liệu mới nhất

```bash
# Thu thập incremental (chỉ dữ liệu mới)
stock-collector collect-daily

# Chỉ thu thập giá
stock-collector collect-daily --type price
```

### Status — Xem trạng thái

```bash
stock-collector status
```

## Cấu trúc Database

| Bảng | Mô tả |
|---|---|
| `stock_listings` | Danh sách mã CK |
| `daily_prices` | Giá OHLCV hằng ngày |
| `financial_income_statements` | Báo cáo kết quả kinh doanh |
| `financial_balance_sheets` | Bảng cân đối kế toán |
| `market_indices` | Chỉ số thị trường |
| `collection_logs` | Log thu thập dữ liệu |

## Cấu trúc Project

```
Stock_VN/
├── Dockerfile                          # Docker build
├── pyproject.toml
├── .env
├── config.yaml
├── src/stock_collector/
│   ├── cli.py           # CLI commands
│   ├── config.py        # Configuration
│   ├── db/
│   │   ├── engine.py    # SQLAlchemy engine
│   │   └── models.py    # ORM models
│   └── collectors/
│       ├── base.py      # Base collector
│       ├── listing.py   # Stock listing
│       ├── price.py     # Daily prices
│       ├── financial.py # Financial data
│       └── index.py     # Market indices
└── README.md
```
