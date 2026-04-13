"""Fetch Polish Wikipedia summaries for politicians."""

import logging
import time
from typing import List, Dict, Any, Optional

import requests

logger = logging.getLogger('miroshark.context.wikipedia')

WIKI_API = 'https://pl.wikipedia.org/w/api.php'


class WikipediaClient:
    """Fetches Polish Wikipedia extracts for politicians."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PoliticalHub/1.0 (miroshark; political intelligence)'
        })

    def get_politician_summary(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Fetch Wikipedia extract for a politician by name.
        Returns dict with title, extract, url or None if not found.
        """
        try:
            # Step 1: Search for the page
            search_params = {
                'action': 'query',
                'list': 'search',
                'srsearch': f'{name} polityk',
                'srlimit': 3,
                'format': 'json',
            }
            resp = self.session.get(WIKI_API, params=search_params, timeout=15)
            resp.raise_for_status()
            search_results = resp.json().get('query', {}).get('search', [])

            if not search_results:
                return None

            # Find best match — prefer exact name match
            best_title = search_results[0]['title']
            for sr in search_results:
                if name.lower() in sr['title'].lower():
                    best_title = sr['title']
                    break

            # Step 2: Get extract
            extract_params = {
                'action': 'query',
                'titles': best_title,
                'prop': 'extracts|info',
                'exintro': True,
                'explaintext': True,
                'exsectionformat': 'plain',
                'inprop': 'url',
                'format': 'json',
            }
            resp = self.session.get(WIKI_API, params=extract_params, timeout=15)
            resp.raise_for_status()
            pages = resp.json().get('query', {}).get('pages', {})

            for page_id, page in pages.items():
                if page_id == '-1':
                    continue
                extract = page.get('extract', '')
                if not extract or len(extract) < 50:
                    continue

                return {
                    'title': page.get('title', best_title),
                    'extract': extract[:3000],  # Cap at 3000 chars
                    'url': page.get('fullurl', f'https://pl.wikipedia.org/wiki/{best_title}'),
                }

            return None

        except Exception as e:
            logger.warning(f"Wikipedia fetch failed for '{name}': {e}")
            return None

    def fetch_batch(self, names: List[str], delay: float = 0.5) -> List[Dict[str, Any]]:
        """
        Fetch Wikipedia summaries for a batch of politician names.
        Respects rate limiting with delay between requests.
        Returns list of successfully fetched summaries.
        """
        results = []
        for i, name in enumerate(names):
            summary = self.get_politician_summary(name)
            if summary:
                summary['politician_name'] = name
                results.append(summary)

            if i < len(names) - 1:
                time.sleep(delay)

            if (i + 1) % 50 == 0:
                logger.info(f"Wikipedia progress: {i + 1}/{len(names)} ({len(results)} found)")

        logger.info(f"Wikipedia batch complete: {len(results)}/{len(names)} politicians found")
        return results
