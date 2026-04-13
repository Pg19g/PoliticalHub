# Context Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Polish political context layer to MiroShark that ingests news (RSS), Sejm data, and polls, then enriches simulation agents with real-world political knowledge.

**Architecture:** Python module inside `backend/app/context/` — direct import in `OasisProfileGenerator._build_entity_context()` as 6th context layer. Data flows: RSS feeds + Sejm API → Neo4j (entities/relations) + Qdrant (vector search on news). Scheduler runs ingestion cron jobs inside Flask app.

**Tech Stack:** Python 3.11, Flask, Neo4j (existing), Qdrant (new), Redis (new), feedparser, APScheduler, qdrant-client, OpenAI SDK (for embeddings via OpenRouter)

---

## File Structure

```
backend/app/context/
├── __init__.py                      # Module init, exports
├── config.py                        # Context-specific config (env vars)
├── ingestion/
│   ├── __init__.py
│   ├── rss_fetcher.py               # Fetch + parse 15 Polish RSS feeds
│   └── sejm_client.py               # api.sejm.gov.pl client (MPs, votes, bills)
├── storage/
│   ├── __init__.py
│   ├── neo4j_political.py           # Create/update political nodes + relationships
│   └── qdrant_store.py              # Qdrant collection CRUD + vector search
├── embedding/
│   ├── __init__.py
│   └── embedder.py                  # Batch text → vector via OpenRouter
├── enrichment/
│   ├── __init__.py
│   └── political_enricher.py        # Query context → assembled context package
└── scheduler.py                     # APScheduler jobs (RSS, embed, Sejm sync)

Modified files:
├── backend/app/config.py                          # Add QDRANT_URL, REDIS_URL, SEJM_TERM
├── backend/app/__init__.py                        # Register scheduler + context blueprint
├── backend/app/services/oasis_profile_generator.py # Hook enricher in _build_entity_context
├── backend/pyproject.toml                         # Add dependencies
```

---

### Task 1: Dependencies and Config

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`
- Create: `backend/app/context/__init__.py`
- Create: `backend/app/context/config.py`

- [ ] **Step 1: Add Python dependencies to pyproject.toml**

Add to the `dependencies` list in `backend/pyproject.toml`:

```python
    # Context Worker — political intelligence layer
    "feedparser>=6.0.0",
    "qdrant-client>=1.9.0",
    "redis>=5.0.0",
    "APScheduler>=3.10.0",
```

- [ ] **Step 2: Add config class for Context Worker**

Create `backend/app/context/__init__.py`:

```python
"""
Polish Political Context Layer for MiroShark

Ingests RSS news, Sejm API data, and polls.
Enriches simulation agents with real-world political knowledge.
"""
```

Create `backend/app/context/config.py`:

```python
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
```

- [ ] **Step 3: Commit**

```bash
cd /tmp/PoliticalHub
git add backend/pyproject.toml backend/app/context/
git commit -m "feat: add context worker config and dependencies"
```

---

### Task 2: Qdrant Store

**Files:**
- Create: `backend/app/context/storage/__init__.py`
- Create: `backend/app/context/storage/qdrant_store.py`

- [ ] **Step 1: Create Qdrant storage module**

Create `backend/app/context/storage/__init__.py`:

```python
from .qdrant_store import QdrantStore
from .neo4j_political import Neo4jPolitical

__all__ = ["QdrantStore", "Neo4jPolitical"]
```

Create `backend/app/context/storage/qdrant_store.py`:

```python
"""Qdrant vector store for political news articles."""

import logging
import uuid
from typing import List, Dict, Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, Range,
    models,
)

from ..config import ContextConfig

logger = logging.getLogger('miroshark.context.qdrant')


class QdrantStore:
    """Manages the political_news Qdrant collection."""

    def __init__(self, url: Optional[str] = None):
        self.url = url or ContextConfig.QDRANT_URL
        self.collection = ContextConfig.QDRANT_COLLECTION
        self.client = QdrantClient(url=self.url, timeout=30)
        self._ensure_collection()

    def _ensure_collection(self):
        """Create collection if it doesn't exist."""
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection not in collections:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=ContextConfig.EMBEDDING_DIMENSIONS,
                    distance=Distance.COSINE,
                ),
            )
            # Create payload indexes for filtering
            for field in ['source', 'published_at']:
                self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD
                    if field == 'source'
                    else models.PayloadSchemaType.KEYWORD,
                )
            logger.info(f"Created Qdrant collection '{self.collection}'")

    def upsert_articles(self, articles: List[Dict[str, Any]], vectors: List[List[float]]):
        """Upsert articles with their embedding vectors."""
        if not articles:
            return

        points = []
        for article, vector in zip(articles, vectors):
            point_id = article.get('id') or str(uuid.uuid4())
            points.append(PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    'title': article['title'],
                    'content': article.get('content', '')[:2000],
                    'source': article['source'],
                    'url': article['url'],
                    'published_at': article['published_at'],
                    'politicians_mentioned': article.get('politicians_mentioned', []),
                    'parties_mentioned': article.get('parties_mentioned', []),
                    'topics': article.get('topics', []),
                },
            ))

        self.client.upsert(collection_name=self.collection, points=points)
        logger.info(f"Upserted {len(points)} articles to Qdrant")

    def search(
        self,
        query_vector: List[float],
        limit: int = 5,
        source_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search over political news."""
        search_filter = None
        if source_filter:
            search_filter = Filter(must=[
                FieldCondition(key='source', match=MatchValue(value=source_filter))
            ])

        results = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            limit=limit,
            query_filter=search_filter,
            with_payload=True,
        )

        return [
            {**hit.payload, 'score': hit.score}
            for hit in results.points
        ]

    def count(self) -> int:
        """Return total number of articles in collection."""
        info = self.client.get_collection(self.collection)
        return info.points_count
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/context/storage/
git commit -m "feat: add Qdrant store for political news vectors"
```

---

### Task 3: Neo4j Political Graph

**Files:**
- Create: `backend/app/context/storage/neo4j_political.py`

- [ ] **Step 1: Create Neo4j political entities module**

Create `backend/app/context/storage/neo4j_political.py`:

```python
"""Neo4j storage for Polish political entities and relationships."""

import logging
from typing import List, Dict, Any, Optional

from ...storage import Neo4jStorage

logger = logging.getLogger('miroshark.context.neo4j_political')


class Neo4jPolitical:
    """CRUD for political entities in the existing Neo4j instance."""

    def __init__(self, storage: Neo4jStorage):
        self.storage = storage
        self._ensure_constraints()

    def _ensure_constraints(self):
        """Create uniqueness constraints for political nodes."""
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Politician) REQUIRE p.sejm_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Party) REQUIRE p.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (b:Bill) REQUIRE b.number IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Committee) REQUIRE c.name IS UNIQUE",
        ]
        with self.storage.driver.session() as session:
            for cypher in constraints:
                try:
                    session.run(cypher)
                except Exception as e:
                    logger.warning(f"Constraint creation warning: {e}")
        logger.info("Political graph constraints ensured")

    def upsert_politician(self, data: Dict[str, Any]):
        """Create or update a Politician node."""
        cypher = """
        MERGE (p:Politician {sejm_id: $sejm_id})
        SET p.name = $name,
            p.party = $party,
            p.role = $role,
            p.district = $district,
            p.photo_url = $photo_url,
            p.updated_at = datetime()
        WITH p
        MERGE (party:Party {name: $party})
        MERGE (p)-[:MEMBER_OF]->(party)
        """
        with self.storage.driver.session() as session:
            session.run(cypher, **data)

    def upsert_bill(self, data: Dict[str, Any]):
        """Create or update a Bill node."""
        cypher = """
        MERGE (b:Bill {number: $number})
        SET b.title = $title,
            b.category = $category,
            b.status = $status,
            b.date = $date,
            b.updated_at = datetime()
        """
        with self.storage.driver.session() as session:
            session.run(cypher, **data)

    def record_vote(self, sejm_id: int, bill_number: str, vote: str):
        """Record a politician's vote on a bill."""
        cypher = """
        MATCH (p:Politician {sejm_id: $sejm_id})
        MATCH (b:Bill {number: $bill_number})
        MERGE (p)-[v:VOTED]->(b)
        SET v.vote = $vote, v.recorded_at = datetime()
        """
        with self.storage.driver.session() as session:
            session.run(cypher, sejm_id=sejm_id, bill_number=bill_number, vote=vote)

    def upsert_committee(self, name: str, committee_type: str):
        """Create or update a Committee node."""
        cypher = """
        MERGE (c:Committee {name: $name})
        SET c.type = $type, c.updated_at = datetime()
        """
        with self.storage.driver.session() as session:
            session.run(cypher, name=name, type=committee_type)

    def set_committee_membership(self, sejm_id: int, committee_name: str):
        """Link a politician to a committee."""
        cypher = """
        MATCH (p:Politician {sejm_id: $sejm_id})
        MATCH (c:Committee {name: $committee_name})
        MERGE (p)-[:SITS_ON]->(c)
        """
        with self.storage.driver.session() as session:
            session.run(cypher, sejm_id=sejm_id, committee_name=committee_name)

    def update_polls(self, polls: Dict[str, float]):
        """Update party poll percentages. Input: {"PiS": 32.1, "KO": 30.5, ...}"""
        cypher = """
        MERGE (p:Party {name: $name})
        SET p.polls_pct = $pct, p.polls_updated_at = datetime()
        """
        with self.storage.driver.session() as session:
            for party_name, pct in polls.items():
                session.run(cypher, name=party_name, pct=pct)
        logger.info(f"Updated polls for {len(polls)} parties")

    def get_party_stances(self, topic: str) -> List[Dict[str, Any]]:
        """Get party voting patterns on bills matching a topic keyword."""
        cypher = """
        MATCH (p:Politician)-[v:VOTED]->(b:Bill)
        WHERE b.title CONTAINS $topic OR b.category CONTAINS $topic
        MATCH (p)-[:MEMBER_OF]->(party:Party)
        WITH party.name AS party_name,
             v.vote AS vote,
             count(*) AS cnt
        RETURN party_name, vote, cnt
        ORDER BY party_name, cnt DESC
        """
        with self.storage.driver.session() as session:
            result = session.run(cypher, topic=topic)
            return [dict(r) for r in result]

    def get_polls(self) -> Dict[str, float]:
        """Get latest poll percentages for all parties."""
        cypher = """
        MATCH (p:Party)
        WHERE p.polls_pct IS NOT NULL
        RETURN p.name AS name, p.polls_pct AS pct
        ORDER BY p.polls_pct DESC
        """
        with self.storage.driver.session() as session:
            result = session.run(cypher)
            return {r['name']: r['pct'] for r in result}

    def get_politician_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find politician by name (case-insensitive partial match)."""
        cypher = """
        MATCH (p:Politician)
        WHERE toLower(p.name) CONTAINS toLower($name)
        OPTIONAL MATCH (p)-[:MEMBER_OF]->(party:Party)
        RETURN p.name AS name, p.sejm_id AS sejm_id, p.role AS role,
               party.name AS party, party.polls_pct AS party_polls
        LIMIT 5
        """
        with self.storage.driver.session() as session:
            result = session.run(cypher, name=name)
            records = [dict(r) for r in result]
            return records[0] if records else None
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/context/storage/neo4j_political.py
git commit -m "feat: add Neo4j political graph CRUD (politicians, bills, votes)"
```

---

### Task 4: Embedder

**Files:**
- Create: `backend/app/context/embedding/__init__.py`
- Create: `backend/app/context/embedding/embedder.py`

- [ ] **Step 1: Create embedding module**

Create `backend/app/context/embedding/__init__.py`:

```python
from .embedder import Embedder

__all__ = ["Embedder"]
```

Create `backend/app/context/embedding/embedder.py`:

```python
"""Batch text embedding via OpenRouter (OpenAI-compatible API)."""

import logging
from typing import List

from openai import OpenAI

from ...config import Config
from ..config import ContextConfig

logger = logging.getLogger('miroshark.context.embedder')


class Embedder:
    """Generates text embeddings using the configured embedding provider."""

    def __init__(self):
        self.client = OpenAI(
            api_key=Config.EMBEDDING_API_KEY or Config.LLM_API_KEY,
            base_url=Config.EMBEDDING_BASE_URL
            if Config.EMBEDDING_PROVIDER == 'openai'
            else f"{Config.EMBEDDING_BASE_URL}/v1",
        )
        self.model = ContextConfig.EMBEDDING_MODEL
        self.dimensions = ContextConfig.EMBEDDING_DIMENSIONS

    def embed_texts(self, texts: List[str], batch_size: int = 20) -> List[List[float]]:
        """Embed a list of texts in batches. Returns list of vectors."""
        all_vectors = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            # Truncate each text to ~8000 chars to stay within token limits
            batch = [t[:8000] for t in batch]

            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                    dimensions=self.dimensions,
                )
                vectors = [item.embedding for item in response.data]
                all_vectors.extend(vectors)
            except Exception as e:
                logger.error(f"Embedding batch failed: {e}")
                # Return zero vectors for failed batch
                all_vectors.extend([[0.0] * self.dimensions] * len(batch))

        logger.info(f"Embedded {len(texts)} texts in {(len(texts) - 1) // batch_size + 1} batches")
        return all_vectors

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query text."""
        return self.embed_texts([text])[0]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/context/embedding/
git commit -m "feat: add embedder for political context (OpenRouter)"
```

---

### Task 5: RSS Fetcher

**Files:**
- Create: `backend/app/context/ingestion/__init__.py`
- Create: `backend/app/context/ingestion/rss_fetcher.py`

- [ ] **Step 1: Create RSS ingestion module**

Create `backend/app/context/ingestion/__init__.py`:

```python
from .rss_fetcher import RSSFetcher
from .sejm_client import SejmClient

__all__ = ["RSSFetcher", "SejmClient"]
```

Create `backend/app/context/ingestion/rss_fetcher.py`:

```python
"""Fetch and parse Polish political news RSS feeds."""

import hashlib
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

import feedparser

from ..config import ContextConfig

logger = logging.getLogger('miroshark.context.rss')

# Known Polish politician names for mention detection
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
        self._dedup_ttl = 86400 * 3  # 3 days

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

        for entry in feed.entries[:20]:  # Max 20 per feed per cycle
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
                'politicians_mentioned': [],  # enriched later if needed
                'topics': [],
            })

            self._mark_seen(url)

        return articles
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/context/ingestion/
git commit -m "feat: add RSS fetcher for 15 Polish news feeds"
```

---

### Task 6: Sejm API Client

**Files:**
- Create: `backend/app/context/ingestion/sejm_client.py`

- [ ] **Step 1: Create Sejm API client**

Create `backend/app/context/ingestion/sejm_client.py`:

```python
"""Client for the Polish Sejm public API (api.sejm.gov.pl)."""

import logging
from typing import List, Dict, Any

import requests

from ..config import ContextConfig

logger = logging.getLogger('miroshark.context.sejm')


class SejmClient:
    """Fetches data from the Polish parliament API."""

    def __init__(self):
        self.base = f"{ContextConfig.SEJM_BASE_URL}/sejm/term{ContextConfig.SEJM_TERM}"
        self.timeout = 30

    def _get(self, path: str) -> Any:
        """HTTP GET with error handling."""
        url = f"{self.base}{path}"
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_mps(self) -> List[Dict[str, Any]]:
        """Fetch all MPs for the current term."""
        raw = self._get('/MP')
        mps = []
        for mp in raw:
            mps.append({
                'sejm_id': mp['id'],
                'name': f"{mp.get('firstName', '')} {mp.get('lastName', '')}".strip(),
                'party': mp.get('club', ''),
                'role': mp.get('profession', ''),
                'district': mp.get('districtName', ''),
                'photo_url': f"{self.base}/MP/{mp['id']}/photo",
            })
        logger.info(f"Fetched {len(mps)} MPs from Sejm API")
        return mps

    def get_committees(self) -> List[Dict[str, Any]]:
        """Fetch all parliamentary committees."""
        raw = self._get('/committees')
        committees = []
        for c in raw:
            committees.append({
                'name': c.get('name', ''),
                'code': c.get('code', ''),
                'type': c.get('type', 'standing'),
            })
        logger.info(f"Fetched {len(committees)} committees")
        return committees

    def get_committee_members(self, code: str) -> List[int]:
        """Fetch MP IDs for a committee."""
        try:
            raw = self._get(f'/committees/{code}/members')
            return [m['id'] for m in raw if 'id' in m]
        except Exception as e:
            logger.warning(f"Committee members fetch failed ({code}): {e}")
            return []

    def get_recent_votings(self, sitting: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch votings for a sitting."""
        try:
            raw = self._get(f'/votings/{sitting}')
            votings = []
            for v in raw[:limit]:
                votings.append({
                    'sitting': sitting,
                    'number': v.get('votingNumber', 0),
                    'title': v.get('topic', ''),
                    'date': v.get('date', ''),
                    'yes': v.get('yes', 0),
                    'no': v.get('no', 0),
                    'abstain': v.get('abstain', 0),
                })
            return votings
        except Exception as e:
            logger.warning(f"Votings fetch failed (sitting {sitting}): {e}")
            return []

    def get_voting_details(self, sitting: int, number: int) -> List[Dict[str, Any]]:
        """Fetch individual MP votes for a specific voting."""
        try:
            raw = self._get(f'/votings/{sitting}/{number}')
            votes = []
            for v in raw.get('votes', []):
                votes.append({
                    'sejm_id': v.get('MP', 0),
                    'vote': v.get('vote', ''),  # "Za", "Przeciw", "Wstrzymał się", "Nieobecny"
                })
            return votes
        except Exception as e:
            logger.warning(f"Voting details fetch failed ({sitting}/{number}): {e}")
            return []

    def get_prints(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent legislative prints (bills)."""
        try:
            raw = self._get('/prints')
            # Sort by number descending (newest first), take limit
            sorted_prints = sorted(raw, key=lambda x: x.get('number', ''), reverse=True)[:limit]
            bills = []
            for p in sorted_prints:
                bills.append({
                    'number': p.get('number', ''),
                    'title': p.get('title', ''),
                    'category': p.get('documentType', ''),
                    'status': 'active',
                    'date': p.get('documentDate', ''),
                })
            logger.info(f"Fetched {len(bills)} recent prints")
            return bills
        except Exception as e:
            logger.warning(f"Prints fetch failed: {e}")
            return []
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/context/ingestion/sejm_client.py
git commit -m "feat: add Sejm API client (MPs, committees, votings, bills)"
```

---

### Task 7: Political Enricher

**Files:**
- Create: `backend/app/context/enrichment/__init__.py`
- Create: `backend/app/context/enrichment/political_enricher.py`

- [ ] **Step 1: Create the enrichment module**

Create `backend/app/context/enrichment/__init__.py`:

```python
from .political_enricher import PoliticalEnricher

__all__ = ["PoliticalEnricher"]
```

Create `backend/app/context/enrichment/political_enricher.py`:

```python
"""
Political Enricher — assembles context for MiroShark agent personas.

Called by OasisProfileGenerator._build_entity_context() as the 6th context layer.
Queries Qdrant (recent news) and Neo4j (political graph) to build a
compact context string injected into the agent's persona.
"""

import json
import logging
from typing import Dict, Any, Optional

from ..storage.qdrant_store import QdrantStore
from ..storage.neo4j_political import Neo4jPolitical
from ..embedding.embedder import Embedder

logger = logging.getLogger('miroshark.context.enricher')


class PoliticalEnricher:
    """Assembles political context for simulation agent enrichment."""

    def __init__(
        self,
        qdrant: QdrantStore,
        neo4j_political: Neo4jPolitical,
        embedder: Embedder,
        redis_client=None,
    ):
        self.qdrant = qdrant
        self.neo4j = neo4j_political
        self.embedder = embedder
        self.redis = redis_client
        self._cache_ttl = 300  # 5 min

    def enrich(
        self,
        query: str,
        entity_name: str = '',
        entity_type: str = '',
        limit: int = 5,
    ) -> Dict[str, Any]:
        """
        Build political context package for an agent persona.

        Args:
            query: Simulation topic / document theme
            entity_name: Agent persona name (e.g. "wyborca PiS", "poseł Lewicy")
            entity_type: Entity type string
            limit: Max news articles to retrieve

        Returns:
            Dict with recent_news, party_stances, polls, context_text
        """
        cache_key = f"ctx:enrich:{hash(f'{query}:{entity_name}')}"
        if self.redis:
            cached = self.redis.get(cache_key)
            if cached:
                return json.loads(cached)

        result = {
            'recent_news': [],
            'party_stances': [],
            'voting_history': [],
            'polls': {},
            'context_text': '',
        }

        # 1. Semantic search for recent news
        try:
            query_vector = self.embedder.embed_query(f"{query} {entity_name}")
            news_hits = self.qdrant.search(query_vector=query_vector, limit=limit)
            result['recent_news'] = [
                f"[{h['source']}] {h['title']}" for h in news_hits
            ]
        except Exception as e:
            logger.warning(f"News search failed: {e}")

        # 2. Party stances from voting records
        try:
            # Extract topic keywords from query
            topic_words = [w for w in query.split() if len(w) > 3]
            for word in topic_words[:3]:
                stances = self.neo4j.get_party_stances(word)
                if stances:
                    result['party_stances'].extend(stances)
                    break
        except Exception as e:
            logger.warning(f"Party stances lookup failed: {e}")

        # 3. Current polls
        try:
            result['polls'] = self.neo4j.get_polls()
        except Exception as e:
            logger.warning(f"Polls lookup failed: {e}")

        # 4. Politician info if entity looks like a politician
        politician_info = None
        if entity_name and entity_type in ('politician', 'publicfigure', 'official'):
            try:
                politician_info = self.neo4j.get_politician_by_name(entity_name)
            except Exception as e:
                logger.warning(f"Politician lookup failed: {e}")

        # Assemble context text
        parts = []

        if result['recent_news']:
            parts.append("### Najnowsze wiadomości (kontekst bieżący)\n" +
                         "\n".join(f"- {n}" for n in result['recent_news']))

        if result['polls']:
            polls_str = ", ".join(f"{k}: {v}%" for k, v in result['polls'].items())
            parts.append(f"### Aktualne sondaże\n{polls_str}")

        if result['party_stances']:
            stance_lines = []
            for s in result['party_stances'][:10]:
                stance_lines.append(f"- {s['party_name']}: {s['vote']} ({s['cnt']}x)")
            parts.append("### Głosowania partii w temacie\n" + "\n".join(stance_lines))

        if politician_info:
            parts.append(f"### Profil polityka\n"
                         f"- {politician_info['name']} ({politician_info.get('party', '?')})\n"
                         f"- Rola: {politician_info.get('role', 'poseł')}")

        result['context_text'] = "\n\n".join(parts)

        # Cache
        if self.redis and result['context_text']:
            self.redis.setex(cache_key, self._cache_ttl, json.dumps(result, ensure_ascii=False))

        logger.info(f"Enriched context for '{entity_name}': {len(result['recent_news'])} news, "
                    f"{len(result['party_stances'])} stances, {len(result['polls'])} polls")

        return result
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/context/enrichment/
git commit -m "feat: add PoliticalEnricher — assembles context for agent personas"
```

---

### Task 8: Scheduler

**Files:**
- Create: `backend/app/context/scheduler.py`

- [ ] **Step 1: Create APScheduler cron jobs**

Create `backend/app/context/scheduler.py`:

```python
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
        """Manual trigger for Sejm sync (e.g. from admin endpoint)."""
        self._job_sejm_sync()

    def trigger_rss(self):
        """Manual trigger for RSS fetch."""
        self._job_rss_and_embed()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/context/scheduler.py
git commit -m "feat: add context scheduler (RSS every 15min, Sejm daily)"
```

---

### Task 9: Hook into MiroShark

**Files:**
- Modify: `backend/app/__init__.py`
- Modify: `backend/app/services/oasis_profile_generator.py`

- [ ] **Step 1: Initialize context layer in Flask app factory**

In `backend/app/__init__.py`, add after the Neo4jStorage initialization block (after line 59):

```python
    # --- Initialize Context Layer (political intelligence) ---
    from .context.config import ContextConfig
    if ContextConfig.ENABLED:
        try:
            from .context.storage.qdrant_store import QdrantStore
            from .context.storage.neo4j_political import Neo4jPolitical
            from .context.embedding.embedder import Embedder
            from .context.enrichment.political_enricher import PoliticalEnricher
            from .context.scheduler import ContextScheduler

            redis_client = None
            if ContextConfig.REDIS_URL:
                import redis
                redis_client = redis.from_url(ContextConfig.REDIS_URL, decode_responses=True)

            qdrant = QdrantStore()
            neo4j_pol = Neo4jPolitical(neo4j_storage) if neo4j_storage else None
            embedder = Embedder()
            enricher = PoliticalEnricher(qdrant, neo4j_pol, embedder, redis_client)

            app.extensions['political_enricher'] = enricher

            # Start scheduler (only in reloader subprocess to avoid double-start)
            if neo4j_pol and (not debug_mode or is_reloader_process):
                ctx_scheduler = ContextScheduler(qdrant, neo4j_pol, embedder, redis_client)
                ctx_scheduler.start()
                app.extensions['context_scheduler'] = ctx_scheduler

            if should_log_startup:
                logger.info("Political context layer initialized (Qdrant + Neo4j + scheduler)")
        except Exception as e:
            logger.warning(f"Political context layer failed to initialize: {e}")
            app.extensions['political_enricher'] = None
    else:
        app.extensions['political_enricher'] = None
```

- [ ] **Step 2: Hook enricher into OasisProfileGenerator._build_entity_context**

In `backend/app/services/oasis_profile_generator.py`, at the end of `_build_entity_context()` method (after the web enrichment block around line 575, before the final `return`), add:

```python
        # 6. Political context enrichment — inject Polish political knowledge
        try:
            from flask import current_app
            enricher = current_app.extensions.get('political_enricher')
            if enricher:
                entity_type = entity.get_entity_type() or "Entity"
                political_ctx = enricher.enrich(
                    query=self.simulation_requirement,
                    entity_name=entity.name,
                    entity_type=entity_type.lower(),
                )
                if political_ctx.get('context_text'):
                    context_parts.append("### Polish Political Context\n" + political_ctx['context_text'])
        except Exception as e:
            logger.debug(f"Political enrichment skipped for {entity.name}: {e}")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/__init__.py backend/app/services/oasis_profile_generator.py
git commit -m "feat: wire context layer into Flask app + OasisProfileGenerator"
```

---

### Task 10: Railway Infrastructure (Qdrant + Redis)

**Files:** None (Railway CLI commands only)

- [ ] **Step 1: Add Qdrant service on Railway**

```bash
cd /tmp/PoliticalHub
railway link -p PoliticalHub -e production
railway add --service qdrant
# Then configure via environment edit:
# source.image = qdrant/qdrant
# Add volume at /qdrant/storage
```

- [ ] **Step 2: Add Redis service on Railway**

```bash
railway add --service redis
# source.image = redis:7-alpine
# Add volume at /data
```

- [ ] **Step 3: Configure environment variables**

Set env vars on miroshark service:
```
QDRANT_URL=http://qdrant.railway.internal:6333
REDIS_URL=redis://redis.railway.internal:6379
CONTEXT_ENABLED=true
SEJM_TERM=10
CONTEXT_RSS_INTERVAL_MIN=15
CONTEXT_EMBEDDING_MODEL=openai/text-embedding-3-small
```

- [ ] **Step 4: Push code and verify deployment**

```bash
git push origin main
# Wait for Railway auto-deploy
# Check logs: railway logs (on miroshark service)
# Expected: "Political context layer initialized (Qdrant + Neo4j + scheduler)"
```

- [ ] **Step 5: Verify Sejm sync manually**

```bash
# After deploy, trigger manual sync via logs/health check
# Or wait for initial RSS fetch on startup
# Check Qdrant: should have articles after 15min
# Check Neo4j: should have Politician/Party nodes after manual trigger or 03:00
```
