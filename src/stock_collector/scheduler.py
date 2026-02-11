"""APScheduler-based scheduler for automated daily data collection."""

import logging
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from stock_collector.collectors.financial import FinancialCollector
from stock_collector.collectors.index import IndexCollector
from stock_collector.collectors.listing import ListingCollector
from stock_collector.collectors.price import PriceCollector
from stock_collector.config import AppConfig

logger = logging.getLogger(__name__)


class StockScheduler:
    """Automated scheduler for stock data collection."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.scheduler = BlockingScheduler()
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Handle graceful shutdown."""
        def shutdown(signum, frame):
            logger.info("Shutdown signal received. Stopping scheduler...")
            self.scheduler.shutdown(wait=False)
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

    def _job_update_listing(self):
        """Job: Update stock listing."""
        logger.info("[Scheduler] Running listing update...")
        try:
            collector = ListingCollector(self.config)
            collector.run()
        except Exception as e:
            logger.error(f"[Scheduler] Listing update failed: {e}")

    def _job_collect_prices(self):
        """Job: Collect daily prices (incremental)."""
        logger.info("[Scheduler] Running daily price collection...")
        try:
            collector = PriceCollector(self.config)
            collector.run(mode="incremental")
        except Exception as e:
            logger.error(f"[Scheduler] Price collection failed: {e}")

    def _job_collect_indices(self):
        """Job: Collect market index data (incremental)."""
        logger.info("[Scheduler] Running index collection...")
        try:
            collector = IndexCollector(self.config)
            collector.run(mode="incremental")
        except Exception as e:
            logger.error(f"[Scheduler] Index collection failed: {e}")

    def _job_collect_financials(self):
        """Job: Collect financial statements."""
        logger.info("[Scheduler] Running financial data collection...")
        try:
            collector = FinancialCollector(self.config)
            collector.run(period="quarter")
        except Exception as e:
            logger.error(f"[Scheduler] Financial collection failed: {e}")

    def start(self):
        """Start the scheduler with all configured jobs."""
        sched_config = self.config.scheduler

        # Daily listing update
        self.scheduler.add_job(
            self._job_update_listing,
            CronTrigger(**sched_config.daily_listing_cron),
            id="daily_listing",
            name="Update Stock Listing",
            replace_existing=True,
        )

        # Daily price collection
        self.scheduler.add_job(
            self._job_collect_prices,
            CronTrigger(**sched_config.daily_price_cron),
            id="daily_prices",
            name="Collect Daily Prices",
            replace_existing=True,
        )

        # Daily index collection
        self.scheduler.add_job(
            self._job_collect_indices,
            CronTrigger(**sched_config.daily_index_cron),
            id="daily_indices",
            name="Collect Market Indices",
            replace_existing=True,
        )

        # Weekly financial data
        self.scheduler.add_job(
            self._job_collect_financials,
            CronTrigger(**sched_config.weekly_financial_cron),
            id="weekly_financials",
            name="Collect Financial Statements",
            replace_existing=True,
        )

        # Print schedule info
        logger.info("=" * 60)
        logger.info("Stock Collector Scheduler Started")
        logger.info("=" * 60)
        logger.info(f"  Listing update : {sched_config.daily_listing_cron}")
        logger.info(f"  Price collection: {sched_config.daily_price_cron}")
        logger.info(f"  Index collection: {sched_config.daily_index_cron}")
        logger.info(f"  Financial data  : {sched_config.weekly_financial_cron}")
        logger.info("=" * 60)
        logger.info("Press Ctrl+C to stop.")

        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")
