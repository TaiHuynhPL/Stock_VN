# Vietnamese Stock Market Data Collector 🇻🇳

Ứng dụng Python tự động thu thập dữ liệu chứng khoán Việt Nam và lưu vào PostgreSQL.

## Tính năng

- 📋 Thu thập danh sách tất cả mã chứng khoán (HOSE, HNX, UPCOM)
- 📈 Thu thập dữ liệu giá OHLCV hằng ngày cho tất cả mã CK
- 📊 Thu thập dữ liệu chỉ số thị trường (VNINDEX, HNX-INDEX, UPCOM-INDEX)
- 💰 Thu thập báo cáo tài chính (BCTC, CĐKT)
- ⏰ Tự động chạy hằng ngày qua GitHub Actions
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

### Schedule — Tự động hóa (local)

```bash
# Bật scheduler chạy liên tục (cần giữ terminal mở)
stock-collector schedule
```

### Status — Xem trạng thái

```bash
stock-collector status
```

## 🚀 Triển Khai Tự Động (GitHub Actions + Supabase)

Chạy tự động trên cloud, **không cần mở máy tính**.

### Bước 1: Tạo Cloud Database (Supabase)

1. Đăng ký tại [supabase.com](https://supabase.com)
2. Tạo project mới → chọn region **Singapore** (gần VN)
3. Lấy thông tin kết nối tại **Settings → Database**:
   - Host: `db.xxxxxxxxxxxx.supabase.co`
   - Port: `5432`
   - Database: `postgres`
   - User: `postgres`
   - Password: password bạn đặt khi tạo project

### Bước 2: Khởi tạo bảng trên Supabase

Cập nhật `.env` với thông tin Supabase rồi chạy:

```bash
# Cập nhật .env trỏ sang Supabase
DB_HOST=db.xxxxxxxxxxxx.supabase.co
DB_USER=postgres
DB_PASSWORD=your_supabase_password

# Tạo tables
stock-collector init-db
```

### Bước 3: Push code lên GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/Stock_VN.git
git push -u origin main
```

### Bước 4: Cấu hình GitHub Secrets

Vào **repo GitHub → Settings → Secrets and variables → Actions → New repository secret**:

| Secret Name | Value |
|---|---|
| `DB_HOST` | `db.xxxxxxxxxxxx.supabase.co` |
| `DB_PORT` | `5432` |
| `DB_NAME` | `postgres` |
| `DB_USER` | `postgres` |
| `DB_PASSWORD` | Password Supabase của bạn |
| `VNSTOCK_API_KEY` | API key từ vnstock.site |

### Bước 5: Xong! 🎉

GitHub Actions sẽ tự động chạy theo lịch:

| Thời gian (VN) | Công việc |
|---|---|
| **17:00** T2-T6 | Cập nhật danh sách mã CK |
| **17:30** T2-T6 | Thu thập giá mới nhất |
| **17:45** T2-T6 | Thu thập chỉ số thị trường |
| **08:00** Thứ 7 | Thu thập báo cáo tài chính |

Chạy thủ công: Vào **Actions → Stock Collector → Run workflow**.

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
├── .github/workflows/stock-collector.yml  # GitHub Actions
├── pyproject.toml
├── .env
├── config.yaml
├── src/stock_collector/
│   ├── cli.py           # CLI commands
│   ├── config.py        # Configuration
│   ├── scheduler.py     # APScheduler (local)
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
