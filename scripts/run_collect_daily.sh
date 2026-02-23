#!/usr/bin/env bash
# ============================================================
# run_collect_daily.sh — Thu thập dữ liệu chứng khoán hàng ngày
# ============================================================
#
# Sử dụng:
#   bash scripts/run_collect_daily.sh
#
# Crontab (tuỳ chọn):
#   30 17 * * 1-5 /absolute/path/to/Stock_VN/scripts/run_collect_daily.sh >> /absolute/path/to/Stock_VN/logs/cron.log 2>&1
#
# ============================================================

set -euo pipefail

# Đường dẫn gốc của project (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo "📈 Stock Collector — Daily Collection"
echo "🕐 $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "📂 Project: $PROJECT_DIR"
echo "============================================"

# Di chuyển vào project directory
cd "$PROJECT_DIR"

# Activate virtualenv nếu có
if [ -d "$PROJECT_DIR/.venv" ]; then
    echo "🐍 Activating virtualenv..."
    source "$PROJECT_DIR/.venv/bin/activate"
fi

# Tạo thư mục logs nếu chưa có
mkdir -p "$PROJECT_DIR/logs"

echo ""
echo "📋 Step 1/4: Updating stock listing..."
stock-collector collect-daily --type listing

echo ""
echo "📈 Step 2/4: Collecting daily prices..."
stock-collector collect-daily --type price

echo ""
echo "📊 Step 3/4: Collecting market indices..."
stock-collector collect-daily --type index

echo ""
echo "💰 Step 4/4: Collecting financial data..."
stock-collector collect-daily --type financial

echo ""
echo "📊 Collection status:"
stock-collector status -n 10

echo ""
echo "============================================"
echo "✅ Daily collection completed!"
echo "🕐 $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "============================================"
