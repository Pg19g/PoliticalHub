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
