"""Fetch and parse Polish political news RSS feeds."""

import hashlib
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

import feedparser

from ..config import ContextConfig

logger = logging.getLogger('miroshark.context.rss')

_PARTY_KEYWORDS = {
    'PiS': ['PiS', 'Prawo i Sprawiedliwość', 'Kaczyński'],
    'KO': ['KO', 'Koalicja Obywatelska', 'Platforma', 'Tusk'],
    'Lewica': ['Lewica', 'Czarzasty', 'Biedroń', 'Zandberg'],
    'PSL': ['PSL', 'Kosiniak-Kamysz', 'Trzecia Droga'],
    'Polska2050': ['Polska 2050', 'Hołownia'],
    'Konfederacja': ['Konfederacja', 'Bosak', 'Mentzen', 'Korwin'],
}


def _detect_parties(text: str) -> List[str]:
    """Detect party mentions in text."""
    found = []
    for party, keywords in _PARTY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                found.append(party)
                break
    return found


def _url_hash(url: str) -> str:
    """Short hash for dedup."""
    return hashlib.md5(url.encode()).hexdigest()[:16]


def _clean_html(raw: str) -> str:
    """Strip HTML tags from RSS content."""
    return re.sub(r'<[^>]+>', '', raw or '').strip()


class RSSFetcher:
    """Fetches and parses Polish news RSS feeds."""

    def __init__(self, redis_client=None):
        self.feeds = ContextConfig.RSS_FEEDS
        self.redis = redis_client
        self._dedup_ttl = 86400 * 3

    def _is_seen(self, url: str) -> bool:
        """Check if URL was already fetched (Redis dedup)."""
        if not self.redis:
            return False
        return self.redis.exists(f"rss:seen:{_url_hash(url)}")

    def _mark_seen(self, url: str):
        """Mark URL as fetched."""
        if self.redis:
            self.redis.setex(f"rss:seen:{_url_hash(url)}", self._dedup_ttl, '1')

    def fetch_all(self) -> List[Dict[str, Any]]:
        """Fetch all configured feeds, return new articles."""
        all_articles = []

        for feed_config in self.feeds:
            try:
                articles = self._fetch_feed(feed_config)
                all_articles.extend(articles)
            except Exception as e:
                logger.warning(f"Feed {feed_config['name']} failed: {e}")

        logger.info(f"Fetched {len(all_articles)} new articles from {len(self.feeds)} feeds")
        return all_articles

    def _fetch_feed(self, feed_config: Dict[str, str]) -> List[Dict[str, Any]]:
        """Fetch a single RSS feed."""
        feed = feedparser.parse(feed_config['url'])
        articles = []

        for entry in feed.entries[:20]:
            url = entry.get('link', '')
            if not url or self._is_seen(url):
                continue

            title = entry.get('title', '')
            content = _clean_html(
                entry.get('summary', '') or
                entry.get('description', '')
            )
            text = f"{title} {content}"

            published = entry.get('published', '')
            try:
                dt = datetime(*entry.published_parsed[:6]) if entry.get('published_parsed') else datetime.now()
                published_at = dt.strftime('%Y-%m-%d')
            except Exception:
                published_at = datetime.now().strftime('%Y-%m-%d')

            articles.append({
                'id': _url_hash(url),
                'title': title,
                'content': content,
                'source': feed_config['name'],
                'url': url,
                'published_at': published_at,
                'orientation': feed_config['orientation'],
                'parties_mentioned': _detect_parties(text),
                'politicians_mentioned': [],
                'topics': [],
            })

            self._mark_seen(url)

        return articles
