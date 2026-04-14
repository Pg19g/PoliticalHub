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
        persona_store=None,
    ):
        self.qdrant = qdrant
        self.neo4j = neo4j_political
        self.embedder = embedder
        self.redis = redis_client
        self.persona_store = persona_store
        self._cache_ttl = 300

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

        # 5. Rich persona from Gemini-generated profiles
        persona_text = None
        if self.persona_store:
            try:
                party_name = ""
                if politician_info:
                    party_name = politician_info.get("party", "")
                persona_text = self.persona_store.get_persona_for_agent(entity_name, party_name)
            except Exception as e:
                logger.warning(f"Persona lookup failed: {e}")

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

        if persona_text:
            parts.append(persona_text)

        # 6. Voter archetype — communication style from data, not LLM training
        try:
            from ..data.voter_archetypes import get_archetype_for_entity_type, format_archetype_for_prompt
            archetype = get_archetype_for_entity_type(entity_type, entity_name)
            if archetype:
                parts.append(format_archetype_for_prompt(archetype))
        except Exception as e:
            logger.debug(f"Archetype lookup skipped: {e}")

        result['context_text'] = "\n\n".join(parts)

        # Cache
        if self.redis and result['context_text']:
            self.redis.setex(cache_key, self._cache_ttl, json.dumps(result, ensure_ascii=False))

        logger.info(f"Enriched context for '{entity_name}': {len(result['recent_news'])} news, "
                    f"{len(result['party_stances'])} stances, {len(result['polls'])} polls")

        return result
