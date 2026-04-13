"""Scheduler for context ingestion jobs (RSS fetch, embed, Sejm sync)."""

import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

from .config import ContextConfig
from .ingestion.rss_fetcher import RSSFetcher
from .ingestion.sejm_client import SejmClient
from .storage.qdrant_store import QdrantStore
from .storage.neo4j_political import Neo4jPolitical
from .embedding.embedder import Embedder

logger = logging.getLogger('miroshark.context.scheduler')


class ContextScheduler:
    """Manages background jobs for political data ingestion."""

    def __init__(
        self,
        qdrant: QdrantStore,
        neo4j_political: Neo4jPolitical,
        embedder: Embedder,
        redis_client=None,
    ):
        self.qdrant = qdrant
        self.neo4j_political = neo4j_political
        self.embedder = embedder
        self.rss_fetcher = RSSFetcher(redis_client=redis_client)
        self.sejm_client = SejmClient()
        self.scheduler = BackgroundScheduler()

    def start(self):
        """Register and start all cron jobs."""
        interval = ContextConfig.RSS_INTERVAL_MIN

        self.scheduler.add_job(
            self._job_rss_and_embed,
            'interval',
            minutes=interval,
            id='rss_fetch_embed',
            name='RSS fetch + embed',
        )

        self.scheduler.add_job(
            self._job_sejm_sync,
            'cron',
            hour=3, minute=0,
            id='sejm_sync',
            name='Sejm API daily sync',
        )

        self.scheduler.start()
        logger.info(f"Context scheduler started (RSS every {interval}min, Sejm daily 03:00)")

        # Run initial RSS fetch on startup
        try:
            self._job_rss_and_embed()
        except Exception as e:
            logger.warning(f"Initial RSS fetch failed: {e}")

    def stop(self):
        """Shutdown scheduler."""
        self.scheduler.shutdown(wait=False)

    def _job_rss_and_embed(self):
        """Fetch RSS feeds, embed new articles, store in Qdrant."""
        try:
            articles = self.rss_fetcher.fetch_all()
            if not articles:
                logger.info("No new articles to embed")
                return

            texts = [f"{a['title']}. {a['content']}" for a in articles]
            vectors = self.embedder.embed_texts(texts)
            self.qdrant.upsert_articles(articles, vectors)

            logger.info(f"RSS pipeline complete: {len(articles)} articles embedded and stored")
        except Exception as e:
            logger.error(f"RSS pipeline failed: {e}")

    def _job_sejm_sync(self):
        """Sync MPs, committees, and recent bills from Sejm API to Neo4j."""
        try:
            # 1. Sync MPs
            mps = self.sejm_client.get_mps()
            for mp in mps:
                self.neo4j_political.upsert_politician(mp)

            # 2. Sync committees + membership
            committees = self.sejm_client.get_committees()
            for c in committees:
                self.neo4j_political.upsert_committee(c['name'], c.get('type', 'standing'))
                members = self.sejm_client.get_committee_members(c['code'])
                for sejm_id in members:
                    self.neo4j_political.set_committee_membership(sejm_id, c['name'])

            # 3. Sync recent bills
            bills = self.sejm_client.get_prints(limit=50)
            for bill in bills:
                self.neo4j_political.upsert_bill(bill)

            logger.info(f"Sejm sync complete: {len(mps)} MPs, {len(committees)} committees, {len(bills)} bills")
        except Exception as e:
            logger.error(f"Sejm sync failed: {e}")

    def trigger_sejm_sync(self):
        """Manual trigger for Sejm sync."""
        self._job_sejm_sync()

    def trigger_rss(self):
        """Manual trigger for RSS fetch."""
        self._job_rss_and_embed()
