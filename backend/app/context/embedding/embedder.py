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
        # Use EMBEDDING_* config (Gemini via OpenAI-compat endpoint)
        # OpenRouter does NOT support embedding models, so we use Gemini directly
        self.client = OpenAI(
            api_key=Config.EMBEDDING_API_KEY,
            base_url=Config.EMBEDDING_BASE_URL,
        )
        self.model = ContextConfig.EMBEDDING_MODEL
        self.dimensions = ContextConfig.EMBEDDING_DIMENSIONS

    def embed_texts(self, texts: List[str], batch_size: int = 20) -> List[List[float]]:
        """Embed a list of texts in batches. Returns list of vectors."""
        all_vectors = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
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
                all_vectors.extend([[0.0] * self.dimensions] * len(batch))

        logger.info(f"Embedded {len(texts)} texts in {(len(texts) - 1) // batch_size + 1} batches")
        return all_vectors

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query text."""
        return self.embed_texts([text])[0]
