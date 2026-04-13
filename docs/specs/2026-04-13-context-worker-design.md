# Context Worker — Polish Political Intelligence Layer

**Date**: 2026-04-13
**Status**: Approved

## Overview

Context Worker is a Python module inside MiroShark backend that ingests Polish political data (news RSS, Sejm API, polls) and enriches simulation agents with real-world political context. Not a separate service — direct import in `OasisProfileGenerator`.

## Architecture

```
backend/app/context/
├── __init__.py
├── config.py                    # Qdrant/RSS/Sejm config
├── ingestion/
│   ├── rss_fetcher.py           # 15 Polish news feeds, every 15min
│   ├── sejm_client.py           # api.sejm.gov.pl (MPs, votes, bills)
│   └── poll_importer.py         # Manual JSON upload
├── embedding/
│   └── embedder.py              # OpenRouter text-embedding-3-small, batch
├── storage/
│   ├── neo4j_political.py       # Political entities CRUD in graph
│   └── qdrant_store.py          # Vector CRUD (news, profile embeddings)
├── enrichment/
│   └── political_enricher.py    # Main: query -> context package
└── scheduler.py                 # APScheduler cron jobs
```

## Data Model

### Neo4j (entities + relationships)

```cypher
(:Politician {name, party, role, sejm_id, twitter})
(:Party {name, ideology, coalition, polls_pct})
(:Bill {title, number, category, status, date})
(:Committee {name, type})

(:Politician)-[:MEMBER_OF]->(:Party)
(:Politician)-[:VOTED {vote: "za"|"przeciw"|"wstrzymał"}]->(:Bill)
(:Politician)-[:SITS_ON]->(:Committee)
(:Party)-[:COALITION_WITH]->(:Party)
```

### Qdrant (collection: `political_news`)

```json
{
  "id": "uuid",
  "vector": [768],
  "payload": {
    "title": "string",
    "content": "string (truncated to 2000 chars)",
    "source": "tvn24|onet|wp|...",
    "url": "string",
    "published_at": "ISO date",
    "politicians_mentioned": ["string"],
    "parties_mentioned": ["string"],
    "topics": ["string"]
  }
}
```

## RSS Feeds (15 sources)

| Source | Orientation |
|--------|------------|
| TVN24, Onet, WP, RMF24, Polsat News | Mainstream |
| PAP | Agency |
| Money.pl, Bankier | Business |
| Gazeta.pl | Center-left |
| Rzeczpospolita | Center |
| Do Rzeczy, wPolityce, Niezalezna | Right |
| OKO.press, Krytyka Polityczna | Left |

## Sejm API (api.sejm.gov.pl)

Public, free, no auth required:
- `GET /sejm/term10/MP` — list of MPs with party, photo, district
- `GET /sejm/term10/votings/{sitting}/{number}` — vote results per MP
- `GET /sejm/term10/prints` — bills/legislation
- `GET /sejm/term10/committees` — committees and membership

Sync frequency: every 24h at 03:00.

## Enrichment API (internal)

```python
enricher = PoliticalEnricher(qdrant_client, neo4j_storage)

result = enricher.enrich(
    query="reakcja na ustawę o mediach",
    entity_name="wyborca PiS",
    entity_type="voter",
    limit=5
)

# Returns:
# {
#   "recent_news": [str, ...],
#   "party_stances": [{"party": str, "stance": str, "quote": str}],
#   "voting_history": [{"bill": str, "result": str}],
#   "polls": {"PiS": 32.1, "KO": 30.5, ...},
#   "context_text": "compiled text for persona injection"
# }
```

Integration point: `oasis_profile_generator.py` calls `enricher.enrich()` inside `_build_entity_context()` as a 6th context layer.

## Scheduler

| Job | Interval | Action |
|-----|----------|--------|
| `fetch_rss` | 15 min | Fetch feeds -> dedup by URL hash -> store raw |
| `embed_new` | 15 min (after fetch) | Batch embed new articles -> upsert vectors |
| `sync_sejm` | 24h (03:00) | MPs, votes, committees -> Neo4j |
| `update_polls` | Manual | JSON upload -> Neo4j Party.polls_pct |

## Infrastructure (Railway)

| Service | Role | Image |
|---------|------|-------|
| miroshark | Flask + Context Worker | Dockerfile (existing) |
| neo4j | Political graph + simulations | neo4j:5.15-community |
| qdrant | Vector search | qdrant/qdrant |
| redis | RSS dedup, enrichment cache (5min TTL) | redis:7-alpine |

## Environment Variables (new)

```
QDRANT_URL=http://qdrant.railway.internal:6333
REDIS_URL=redis://redis.railway.internal:6379
SEJM_TERM=10
CONTEXT_RSS_INTERVAL_MIN=15
CONTEXT_EMBEDDING_MODEL=openai/text-embedding-3-small
```

## Out of Scope

- Social media listening (phase 2)
- Poll dashboard UI (phase 2)
- MemPalace session memory (phase 3)
- Electorate segment creator UI (phase 2)
- Automatic poll scraping (manual import for now)
