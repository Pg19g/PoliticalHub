"""Context Worker configuration — reads from environment variables."""

import os


class ContextConfig:
    """Configuration for the political context layer."""

    ENABLED = os.environ.get('CONTEXT_ENABLED', 'true').lower() == 'true'

    # Qdrant
    QDRANT_URL = os.environ.get('QDRANT_URL', 'http://localhost:6333')
    QDRANT_COLLECTION = 'political_news'

    # Redis (for RSS dedup + enrichment cache)
    REDIS_URL = os.environ.get('REDIS_URL', '')

    # Sejm API
    SEJM_BASE_URL = 'https://api.sejm.gov.pl'
    SEJM_TERM = int(os.environ.get('SEJM_TERM', '10'))

    # Embedding
    EMBEDDING_MODEL = os.environ.get('CONTEXT_EMBEDDING_MODEL', 'openai/text-embedding-3-small')
    EMBEDDING_DIMENSIONS = 768

    # Scheduler intervals
    RSS_INTERVAL_MIN = int(os.environ.get('CONTEXT_RSS_INTERVAL_MIN', '15'))

    # RSS feeds
    RSS_FEEDS = [
        {'name': 'tvn24', 'url': 'https://tvn24.pl/najnowsze.xml', 'orientation': 'mainstream'},
        {'name': 'onet', 'url': 'https://wiadomosci.onet.pl/kraj/rss', 'orientation': 'mainstream'},
        {'name': 'wp', 'url': 'https://wiadomosci.wp.pl/rss.xml', 'orientation': 'mainstream'},
        {'name': 'rmf24', 'url': 'https://www.rmf24.pl/fakty/feed', 'orientation': 'mainstream'},
        {'name': 'polsat', 'url': 'https://www.polsatnews.pl/rss/polska.xml', 'orientation': 'mainstream'},
        {'name': 'pap', 'url': 'https://www.pap.pl/rss.xml', 'orientation': 'agency'},
        {'name': 'money', 'url': 'https://www.money.pl/rss/rss.xml', 'orientation': 'business'},
        {'name': 'gazeta', 'url': 'https://wiadomosci.gazeta.pl/pub/rss/wiadomosci_kraj.htm', 'orientation': 'center-left'},
        {'name': 'dorzeczy', 'url': 'https://dorzeczy.pl/feed/', 'orientation': 'right'},
        {'name': 'wpolityce', 'url': 'https://wpolityce.pl/rss.xml', 'orientation': 'right'},
        {'name': 'niezalezna', 'url': 'https://niezalezna.pl/rss.xml', 'orientation': 'right'},
        {'name': 'oko', 'url': 'https://oko.press/feed', 'orientation': 'left'},
        {'name': 'krytyka', 'url': 'https://krytykapolityczna.pl/feed/', 'orientation': 'left'},
        {'name': 'bankier', 'url': 'https://www.bankier.pl/rss/wiadomosci.xml', 'orientation': 'business'},
        {'name': 'rp', 'url': 'https://www.rp.pl/rss_main', 'orientation': 'center'},
    ]
