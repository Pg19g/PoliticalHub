# Aluqa Swarm Intelligence — Political Intelligence Hub

> Fork MiroShark dostosowany do symulacji reakcji polskiej opinii publicznej na decyzje polityczne.

## Cel projektu

Narzędzie intelligence dla polskich polityków i doradców politycznych. Polityk wrzuca draft tweeta, projekt ustawy lub komunikat prasowy → system symuluje reakcję polskiego internetu z realistycznymi agentami (wyborcy różnych partii, dziennikarze, duchowni, niezdecydowani) → generuje raport z rekomendacjami strategicznymi.

**Wartość**: focus group w 15 minut zamiast 3 tygodni.

## Architektura

```
Railway Project: "PoliticalHub"
├── miroshark      — Flask app + Context Worker (Dockerfile)
├── neo4j          — Graf polityczny + symulacje (neo4j:5.15-community)
├── qdrant         — Vector search na newsach (qdrant/qdrant:v1.17.1)
└── redis          — RSS dedup + cache (redis:7-alpine)
```

**Repo**: https://github.com/Pg19g/PoliticalHub
**Live**: https://miroshark-production-8ec0.up.railway.app
**LLM**: google/gemini-3.1-flash-lite-preview via OpenRouter
**Embeddings**: gemini-embedding-001 via Gemini API

## Co zostało zbudowane

### Context Worker (`backend/app/context/`)
Moduł Python wewnątrz Flask, dostarcza polski kontekst polityczny do symulacji.

| Komponent | Status | Opis |
|-----------|--------|------|
| RSS Fetcher | ✅ Live | 15 polskich feedów (TVN24, Onet, wPolityce, OKO.press...), co 15 min |
| Sejm API Client | ✅ Live | 498 posłów, 40 komisji, 50 ustaw z api.sejm.gov.pl |
| Wikipedia Client | ✅ Live | 98 profili posłów z pl.wikipedia.org |
| Qdrant Store | ✅ Live | ~960 artykułów w bazie wektorowej |
| Neo4j Political Graph | ✅ Live | Politician, Party, Bill, Committee + relacje |
| Persona Generator | ✅ Live | 26 indywidualnych person politycznych + 6 partyjnych (Gemini Search Grounding) |
| Voter Archetypes | ✅ Live | 15 archetypów polskich wyborców z przykładowymi postami |
| Enrichment Pipeline | ✅ Live | Compact context injection (~300 tokenów per agent) |
| Sondaże (polls) | ✅ Live | Dynamiczny rozkład agentów z Neo4j (KO 32%, PiS 29%, Konf 13%...) |
| Requirement Parser | ✅ Live | Parsuje grupy z promptu LUB auto-generuje z sondaży |

### Modyfikacje MiroShark
| Zmiana | Status | Opis |
|--------|--------|------|
| Rebrand → Aluqa | ✅ | Navbar, tytuły, eksporty |
| Polskie prompty (Twitter/Reddit) | ✅ | Agenci piszą po polsku |
| Polskie prompty (Polymarket) | ✅ | Traderzy myślą w PLN |
| Polskie persona generation | ✅ | Bio i opisy po polsku |
| Polskie eventy/config | ✅ | hot_topics, narracja po polsku |
| Raport po polsku | ✅ | Wszystkie sekcje + synteza |
| Sekcja "Rekomendacje Strategiczne" | ✅ | Actionable advice w raporcie |
| Fix do_nothing bias | ✅ | Agenci aktywnie reagują zamiast lurk 90% |
| Fix active_hours | ✅ | Usunięty filtr godzinowy (debata = 24/7) |
| Fix parallel runner | ✅ | Poprawki w run_parallel_simulation.py (właściwy runner) |
| Fix start hour | ✅ | Symulacja startuje o 8:00 nie o 00:00 |
| Party affinity | ✅ | Wyborcy KO popierają KO (nie losowo) |
| Non-actor filter | ✅ | CBOS/ZUS/Fundusz nie stają się agentami |
| Persistent uploads | ✅ | Railway volume na /app/backend/uploads |
| Admin API | ✅ | /api/context/* (status, diagnostics, trigger RSS/Sejm/Wiki/personas/polls) |
| Vite allowedHosts | ✅ | Frontend działa na Railway |
| Relative API URLs | ✅ | Frontend nie hardcoduje localhost:5001 |

### Wyniki testów
- **Symulacja "Tweet Tuska o Funduszu Kościelnym"**: 688 akcji (352 Reddit + 336 Twitter), 33 agentów, 15 rund
- Agenci piszą po polsku, w odpowiednich tonach per partia
- Raport po polsku z sekcją Rekomendacje Strategiczne (17,980 znaków)

## Co zostało do zrobienia

### Priorytet 1 — Jakość symulacji
- [ ] **Weryfikacja party affinity** — przetestować czy wyborcy KO naprawdę popierają KO po ostatnim fixie
- [ ] **Optymalizacja kosztów** — 688 akcji kosztowało ~$4-5 na OpenRouter. Cel: <$2 per symulacja
- [ ] **Smart model routing** — tani model na simulation rounds, drogi na raport (SMART_MODEL_NAME)
- [ ] **Walidacja raportu** — nie generować raportu jeśli <20 akcji
- [ ] **Wikipedia retry** — zwiększyć delay do 2s, retry z backoff. Pobrać brakujących 400 posłów

### Priorytet 2 — UX
- [ ] **Historia symulacji w UI** — symulacje z API nie pojawiają się w UI history
- [ ] **Pole tekstowe w UI** — oprócz file upload, możliwość wklejenia tekstu
- [ ] **Progress indicator** — realne śledzenie postępu symulacji w UI
- [ ] **Polymarket disabled domyślnie** — nie działa w Polsce
- [ ] **Polska domena** — np. aluqa-swarm.pl zamiast miroshark-production-*.railway.app

### Priorytet 3 — Rozszerzenie kontekstu
- [ ] **CBOS scraper** — automatyczny import sondaży (teraz manual via API)
- [ ] **Sejm voting sync** — `get_voting_details()` — zaimportować głosowania posłów
- [ ] **Social listening** — Twitter/X API na polskich polityków (real-time ton dyskusji)
- [ ] **Archetypowe persony faza 2** — kontekst regionalny (Śląsk vs Podlasie), wiekowy (boomer vs zoomer)

### Priorytet 4 — Zaawansowane features
- [ ] **A/B testing komunikatów** — fork symulacji z dwoma wariantami tweeta, porównanie wyników
- [ ] **Sondaż overlay** — porównanie wyników symulacji z realnymi sondażami CBOS/IBRiS
- [ ] **Trend tracking** — jak zmienia się reakcja na podobne tematy w czasie
- [ ] **API dla klientów** — REST API do uruchamiania symulacji programowo
- [ ] **Stripe payments** — monetyzacja per symulacja

## Kluczowe lekcje z sesji

1. **MiroShark używa `run_parallel_simulation.py`**, nie `run_twitter_simulation.py` — fixy muszą iść do właściwego pliku
2. **`active_hours` + `activity_level` filtering** potrafi wyeliminować 100% agentów — symulacja przechodzi 24 rundy z 0 akcjami
3. **`do_nothing` bias** jest w 3 miejscach: prompt, tool docstring (base.py), tool docstring (agent_action.py) — wszystkie muszą być spójne
4. **Simulated time startuje od 00:00** — agenci z active_hours=[9-17] nigdy nie działają w nocy
5. **OpenRouter nie obsługuje embedding models** — użyj Gemini API bezpośrednio
6. **Synthetic entities potrzebują explicit party affinity** — bez tego persona generator tworzy losowe persony

## Struktura plików (nowe/zmodyfikowane)

```
backend/app/
├── context/                           # Context Worker (NOWY moduł)
│   ├── config.py                      # RSS feeds, Qdrant, Sejm config
│   ├── ingestion/
│   │   ├── rss_fetcher.py             # 15 polskich feedów
│   │   ├── sejm_client.py             # api.sejm.gov.pl
│   │   ├── wikipedia_client.py        # pl.wikipedia.org profiles
│   │   └── persona_generator.py       # Gemini Search Grounding personas
│   ├── storage/
│   │   ├── qdrant_store.py            # Vector CRUD
│   │   ├── neo4j_political.py         # Political graph CRUD
│   │   └── persona_store.py           # Persona save/retrieve
│   ├── embedding/
│   │   └── embedder.py                # Gemini embeddings
│   ├── enrichment/
│   │   └── political_enricher.py      # Agent context assembly
│   ├── data/
│   │   └── voter_archetypes.py        # 15 Polish voter archetypes
│   └── scheduler.py                   # APScheduler (RSS, Sejm, Wiki)
├── api/
│   └── context.py                     # Admin endpoints (NOWY)
├── services/
│   └── requirement_parser.py          # Voter groups from requirement (NOWY)
│
backend/wonderwall/                    # MiroShark simulation engine (ZMODYFIKOWANE)
├── simulations/
│   ├── social_media/prompts.py        # Polish Twitter/Reddit prompts
│   ├── polymarket/prompts.py          # Polish Polymarket prompt
│   └── base.py                        # do_nothing bias fix
├── social_agent/
│   ├── agent.py                       # Active participant prompt
│   └── agent_action.py                # do_nothing bias fix
├── scripts/
│   ├── run_parallel_simulation.py     # Activity fix + start hour (KEY FILE)
│   ├── run_twitter_simulation.py      # Activity fix
│   └── run_reddit_simulation.py       # Activity fix
│
backend/app/services/
├── oasis_profile_generator.py         # Polish persona prompts
├── simulation_config_generator.py     # Polish event/topic generation
├── report_agent.py                    # Polish report + Rekomendacje Strategiczne
└── simulation_manager.py             # Requirement parser hook

frontend/
├── index.html                         # Aluqa title
├── src/views/*.vue                    # ALUQA branding
└── src/api/index.js                   # Relative API URLs
```

## Env vars (Railway)

```
# LLM (OpenRouter)
LLM_API_KEY=sk-or-v1-...
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL_NAME=google/gemini-3.1-flash-lite-preview

# Embeddings (Gemini direct)
EMBEDDING_API_KEY=AIzaSy...
EMBEDDING_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
EMBEDDING_MODEL=gemini-embedding-001

# Context Worker
QDRANT_URL=http://qdrant.railway.internal:6333
REDIS_URL=redis://redis.railway.internal:6379
CONTEXT_ENABLED=true
SEJM_TERM=10

# Neo4j
NEO4J_URI=bolt://neo4j.railway.internal:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=miroshark
```

## Admin API

```bash
# Status
GET  /api/context/status
GET  /api/context/diagnostics

# Polls
GET  /api/context/polls
POST /api/context/polls              # Body: {"KO": 32, "PiS": 29, ...}

# Manual triggers
POST /api/context/trigger/rss
POST /api/context/trigger/sejm
POST /api/context/trigger/wiki
POST /api/context/trigger/personas
```
