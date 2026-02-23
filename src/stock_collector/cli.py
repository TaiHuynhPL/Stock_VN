"""CLI entry point for Vietnamese Stock Data Collector."""

import logging
import sys
from datetime import date, datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from stock_collector.config import load_config

console = Console()


def _setup_logging(config):
    """Configure logging based on config."""
    log_dir = Path(config.logging.file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, config.logging.level, logging.INFO),
        format=config.logging.format,
        handlers=[
            logging.FileHandler(config.logging.file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Suppress noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def _init_app():
    """Load config, setup logging, init DB engine."""
    config = load_config()
    _setup_logging(config)

    from stock_collector.db.engine import init_engine
    init_engine(config)
    return config


@click.group()
@click.version_option(version="1.0.0", prog_name="stock-collector")
def cli():
    """🇻🇳 Vietnamese Stock Market Data Collector

    Tự động thu thập dữ liệu chứng khoán Việt Nam và lưu vào PostgreSQL.
    """
    pass


@cli.command()
def init_db():
    """Tạo database schema (tất cả các bảng)."""
    config = _init_app()

    from stock_collector.db.engine import create_all_tables, test_connection

    console.print("\n[bold blue]🔌 Testing database connection...[/]")
    if not test_connection():
        console.print("[bold red]❌ Cannot connect to database. Check your .env configuration.[/]")
        sys.exit(1)

    console.print("[green]✅ Database connection OK[/]")
    console.print("\n[bold blue]📦 Creating tables...[/]")
    create_all_tables()
    console.print("[green]✅ All tables created successfully![/]")

    console.print("\n[bold]Tables created:[/]")
    console.print("  • stock_listings")
    console.print("  • daily_prices")
    console.print("  • financial_income_statements")
    console.print("  • financial_balance_sheets")
    console.print("  • market_indices")
    console.print("  • collection_logs")
    console.print()


@cli.command()
@click.option("--start", "-s", default="2012-01-01", help="Start date (YYYY-MM-DD)")
@click.option("--end", "-e", default=None, help="End date (YYYY-MM-DD, default: today)")
@click.option("--symbols", default=None, help="Comma-separated symbols (default: all)")
@click.option("--type", "-t", "collect_type", default="all",
              type=click.Choice(["all", "price", "index", "financial"]),
              help="Type of data to backfill")
@click.option("--period", default="quarter", type=click.Choice(["year", "quarter"]),
              help="Financial period (for financial type)")
def backfill(start, end, symbols, collect_type, period):
    """Thu thập dữ liệu lịch sử (backfill).

    Chạy lần đầu để lấy toàn bộ dữ liệu trong quá khứ.
    """
    config = _init_app()
    end = end or date.today().strftime("%Y-%m-%d")
    symbol_list = [s.strip().upper() for s in symbols.split(",")] if symbols else None

    console.print(f"\n[bold blue]📥 Backfill from {start} to {end}[/]")
    if symbol_list:
        console.print(f"[dim]Symbols: {', '.join(symbol_list)}[/]")
    console.print()

    # Always update listing first
    if collect_type in ("all", "price"):
        console.print("[bold yellow]📋 Step 1: Updating stock listing...[/]")
        from stock_collector.collectors.listing import ListingCollector
        listing = ListingCollector(config)
        count = listing.run()
        console.print(f"[green]  ✅ {count} symbols updated[/]\n")

    if collect_type in ("all", "price"):
        console.print("[bold yellow]📈 Step 2: Backfilling prices...[/]")
        from stock_collector.collectors.price import PriceCollector
        price = PriceCollector(config)
        count = price.run(mode="backfill", start_date=start, end_date=end, symbols=symbol_list)
        console.print(f"[green]  ✅ {count} price records collected[/]\n")

    if collect_type in ("all", "index"):
        console.print("[bold yellow]📊 Step 3: Backfilling market indices...[/]")
        from stock_collector.collectors.index import IndexCollector
        index = IndexCollector(config)
        count = index.run(mode="backfill", start_date=start, end_date=end)
        console.print(f"[green]  ✅ {count} index records collected[/]\n")

    if collect_type in ("all", "financial"):
        console.print("[bold yellow]💰 Step 4: Backfilling financial statements...[/]")
        from stock_collector.collectors.financial import FinancialCollector
        financial = FinancialCollector(config)
        count = financial.run(symbols=symbol_list, period=period)
        console.print(f"[green]  ✅ {count} financial records collected[/]\n")

    console.print("[bold green]🎉 Backfill completed![/]")


@cli.command("collect-daily")
@click.option("--type", "-t", "collect_type", default="all",
              type=click.Choice(["all", "listing", "price", "index", "financial"]),
              help="Type of data to collect")
def collect_daily(collect_type):
    """Thu thập dữ liệu mới nhất (incremental).

    Chỉ thu thập dữ liệu chưa có trong DB (từ ngày cuối + 1 đến hôm nay).
    """
    config = _init_app()

    console.print(f"\n[bold blue]📥 Incremental daily collection ({collect_type})[/]\n")

    if collect_type in ("all", "listing"):
        console.print("[bold yellow]📋 Updating stock listing...[/]")
        from stock_collector.collectors.listing import ListingCollector
        listing = ListingCollector(config)
        count = listing.run()
        console.print(f"[green]  ✅ {count} symbols[/]\n")

    if collect_type in ("all", "price"):
        console.print("[bold yellow]📈 Collecting new prices (incremental)...[/]")
        from stock_collector.collectors.price import PriceCollector
        price = PriceCollector(config)
        count = price.run(mode="incremental")
        console.print(f"[green]  ✅ {count} new price records[/]\n")

    if collect_type in ("all", "index"):
        console.print("[bold yellow]📊 Collecting market indices (incremental)...[/]")
        from stock_collector.collectors.index import IndexCollector
        index = IndexCollector(config)
        count = index.run(mode="incremental")
        console.print(f"[green]  ✅ {count} new index records[/]\n")

    if collect_type in ("all", "financial"):
        console.print("[bold yellow]💰 Collecting financial data...[/]")
        from stock_collector.collectors.financial import FinancialCollector
        financial = FinancialCollector(config)
        count = financial.run(period="quarter")
        console.print(f"[green]  ✅ {count} financial records[/]\n")

    console.print("[bold green]🎉 Daily collection completed![/]")


@cli.command()
@click.option("--limit", "-n", default=20, help="Number of log entries to show")
def status(limit):
    """Xem trạng thái và lịch sử thu thập dữ liệu."""
    config = _init_app()

    from stock_collector.db.engine import get_session
    from stock_collector.db.models import CollectionLog, DailyPrice, MarketIndex, StockListing
    from sqlalchemy import func

    with get_session() as session:
        # Summary stats
        listings_count = session.query(func.count(StockListing.symbol)).scalar() or 0
        prices_count = session.query(func.count(DailyPrice.id)).scalar() or 0
        indices_count = session.query(func.count(MarketIndex.id)).scalar() or 0

        latest_price_date = session.query(func.max(DailyPrice.trading_date)).scalar()
        latest_index_date = session.query(func.max(MarketIndex.trading_date)).scalar()

        console.print("\n[bold blue]📊 Database Summary[/]")
        summary = Table(show_header=False, box=None, padding=(0, 2))
        summary.add_column(style="bold")
        summary.add_column()
        summary.add_row("Stock Listings", f"{listings_count:,}")
        summary.add_row("Price Records", f"{prices_count:,}")
        summary.add_row("Index Records", f"{indices_count:,}")
        summary.add_row("Latest Price Date", str(latest_price_date or "N/A"))
        summary.add_row("Latest Index Date", str(latest_index_date or "N/A"))
        console.print(summary)

        # Recent collection logs
        console.print(f"\n[bold blue]📜 Recent Collection Logs (last {limit})[/]")
        logs = (
            session.query(CollectionLog)
            .order_by(CollectionLog.started_at.desc())
            .limit(limit)
            .all()
        )

        if not logs:
            console.print("[dim]No collection logs yet.[/]")
        else:
            table = Table(show_lines=True)
            table.add_column("ID", style="dim")
            table.add_column("Type")
            table.add_column("Symbol")
            table.add_column("Status")
            table.add_column("Records", justify="right")
            table.add_column("Started")
            table.add_column("Duration")
            table.add_column("Error")

            for log in logs:
                status_style = {
                    "success": "green",
                    "failed": "red",
                    "running": "yellow",
                }.get(str(log.status), "white")

                duration = ""
                if log.finished_at and log.started_at:  # type: ignore[truthy-bool]
                    delta = log.finished_at - log.started_at
                    duration = f"{delta.total_seconds():.1f}s"

                error_msg = (str(log.error_message)[:50] + "...") if log.error_message else ""  # type: ignore[truthy-bool]

                started_str = ""
                if log.started_at:  # type: ignore[truthy-bool]
                    started_str = log.started_at.strftime("%Y-%m-%d %H:%M")  # type: ignore[union-attr]

                table.add_row(
                    str(log.id),
                    str(log.collection_type),
                    str(log.symbol) if log.symbol else "-",  # type: ignore[truthy-bool]
                    f"[{status_style}]{log.status}[/]",
                    str(log.records_count or 0),
                    started_str,
                    duration,
                    error_msg,
                )

            console.print(table)

    console.print()


if __name__ == "__main__":
    cli()
