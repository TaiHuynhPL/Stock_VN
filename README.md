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

## Lên lịch tự động (Cronjob)

### GitHub Actions (khuyến nghị)

Workflow tự động chạy `collect-daily` lúc **17:30 ICT (thứ 2 → thứ 6)** — sau khi thị trường đóng cửa.

**Thiết lập:**

1. Vào **Supabase Dashboard → Settings → Database → Connection string → chọn tab "Session mode"** và copy connection string
2. Vào GitHub repo **Settings → Secrets and variables → Actions** và thêm các secrets:

> [!IMPORTANT]
> `DB_POOLER_URL` là secret quan trọng nhất — copy nguyên connection string từ Supabase (Session mode). Nếu có secret này, app sẽ tự động dùng pooler thay vì direct connection.

| Secret | Giá trị | Ví dụ |
|---|---|---|
| `DB_POOLER_URL` | **Connection string (Session mode)** | `postgresql://postgres.xxx:password@aws-0-region.pooler.supabase.com:6543/postgres` |
| `DB_HOST` | Direct host (backup) | `db.xxx.supabase.co` |
| `DB_PORT` | Port | `5432` |
| `DB_NAME` | Database name | `postgres` |
| `DB_USER` | Username | `postgres` |
| `DB_PASSWORD` | Password | *(password)* |
| `VNSTOCK_API_KEY` | API key vnstock | `vnstock_xxx...` |

3. Push code, workflow sẽ tự chạy. Chạy thủ công: **Actions → "📈 Daily Stock Data Collection" → Run workflow**

### Crontab Local (tuỳ chọn)

Nếu muốn chạy trên máy local thay vì GitHub Actions:

```bash
# Mở crontab editor
crontab -e

# Thêm dòng sau (chạy 17:30 thứ 2-6):
30 17 * * 1-5 /absolute/path/to/Stock_VN/scripts/run_collect_daily.sh >> /absolute/path/to/Stock_VN/logs/cron.log 2>&1
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
├── .github/workflows/
│   └── collect-daily.yml   # Cronjob GitHub Actions
├── scripts/
│   └── run_collect_daily.sh # Script chạy local
├── Dockerfile
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
