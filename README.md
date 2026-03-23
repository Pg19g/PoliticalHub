<div align="center">

<img src="./miroshark-banner.jpg" alt="MiroShark Logo" width="75%"/>

<em>A Simple and Universal Swarm Intelligence Engine — Run Locally or with Any Cloud API</em>

</div>

## What is this?

**MiroShark** is a multi-agent simulation engine: upload any document (press release, policy draft, financial report), and it generates hundreds of AI agents with unique personalities that simulate public reaction on social media — posts, arguments, opinion shifts — hour by hour.

Runs on **Neo4j** for the knowledge graph and any **OpenAI-compatible API** for inference. Use local Ollama (no cloud needed) or any cloud provider.

## Screenshots

<div align="center">
<table>
<tr>
<td><img src="./screen1.png" width="100%"/></td>
<td><img src="./screen2.png" width="100%"/></td>
</tr>
<tr>
<td><img src="./screen3.png" width="100%"/></td>
<td><img src="./screen4.png" width="100%"/></td>
</tr>
<tr>
<td><img src="./screen5.png" width="100%"/></td>
<td><img src="./screen6.png" width="100%"/></td>
</tr>
</table>
</div>

## How It Works

1. **Graph Build** — Extracts entities and relationships from your document into a Neo4j knowledge graph with per-agent memory.
2. **Agent Setup** — Generates hundreds of personas, each with unique personality, opinion bias, reaction speed, and influence level.
3. **Simulation** — Agents post, reply, argue, and shift opinions on simulated social platforms. Tracks sentiment evolution and influence dynamics in real time. Supports pause, resume, and restart.
4. **Report** — A ReportAgent analyzes the simulation, interviews a focus group, and generates a structured analysis. Reports are cached.
5. **Interaction** — Chat directly with any agent via persona chat, or send questions to groups. Click any agent to view their full profile and simulation history.

## Quick Start

### Prerequisites

- An OpenAI-compatible API key *(including OpenRouter, OpenAI, Anthropic, etc.)* **or** Ollama for local inference
- Python 3.11+, Node.js 18+, Neo4j 5.15+ **or** Docker & Docker Compose

---

### Option A: Cloud API (no GPU needed)

Only Neo4j runs locally. LLM and embeddings use a cloud provider.

```bash
# 1. Start Neo4j (or: brew install neo4j && brew services start neo4j)
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/miroshark \
  neo4j:5.15-community

# 2. Configure
cp .env.example .env
```

Edit `.env` (example using OpenRouter):

```bash
LLM_API_KEY=sk-or-v1-your-key
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL_NAME=qwen/qwen3-235b-a22b-2507

EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=openai/text-embedding-3-small
EMBEDDING_BASE_URL=https://openrouter.ai/api
EMBEDDING_API_KEY=sk-or-v1-your-key
EMBEDDING_DIMENSIONS=768
```

```bash
npm run setup:all && npm run dev
```

Open `http://localhost:3000` — backend API at `http://localhost:5001`.

---

### Option B: Docker — Local Ollama

```bash
git clone https://github.com/aaronjmars/MiroShark.git
cd MiroShark
docker compose up -d

# Pull models into Ollama
docker exec miroshark-ollama ollama pull qwen3.5:27b
docker exec miroshark-ollama ollama pull nomic-embed-text
```

Open `http://localhost:3000`.

---

### Option C: Manual — Local Ollama

```bash
# 1. Start Neo4j
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/miroshark \
  neo4j:5.15-community

# 2. Start Ollama & pull models
ollama serve &
ollama pull qwen3.5:27b
ollama pull nomic-embed-text

# 3. Configure & run
cp .env.example .env
npm run setup:all
npm run dev
```

---

## Configuration

### Recommended Models

A typical simulation runs ~40 turns × 100+ agents. Pick a model that balances cost and quality for that volume.

#### Cloud (OpenRouter)

| Model | ID | Cost/sim | Notes |
|---|---|---|---|
| **Qwen3 235B A22B** ⭐ | `qwen/qwen3-235b-a22b-2507` | ~$0.30 | Best overall |
| GPT-5 Nano | `openai/gpt-5-nano` | ~$0.41 | Budget option |
| Gemini 2.5 Flash Lite | `google/gemini-2.5-flash-lite` | ~$0.58 | Good alt |
| DeepSeek V3.2 | `deepseek/deepseek-v3.2` | ~$1.11 | Stronger agentic reasoning |

**Embeddings:** `openai/text-embedding-3-small` on OpenRouter. Keep `EMBEDDING_DIMENSIONS=768`.

#### Local (Ollama)

> **Context override required.** Ollama defaults to 4096 tokens, but MiroShark prompts need 10–30k. Create a custom Modelfile:
>
> ```bash
> printf 'FROM qwen3:14b\nPARAMETER num_ctx 32768' > Modelfile
> ollama create mirosharkai -f Modelfile
> ```

| Model | VRAM | Speed | Notes |
|---|---|---|---|
| `qwen3.5:27b` | 20GB+ | ~40 t/s | Best quality |
| `qwen3.5:35b-a3b` *(MoE)* | 16GB | ~112 t/s | Fastest — MoE activates only 3B params |
| `qwen3:14b` | 12GB | ~60 t/s | Solid balance |
| `qwen3:8b` | 8GB | ~42 t/s | Minimum viable; 40K context limit |

**Hardware quick-pick:**

| Setup | Model |
|---|---|
| RTX 3090/4090 or M2 Pro 32GB+ | `qwen3.5:27b` |
| RTX 4080 / M2 Pro 16GB | `qwen3.5:35b-a3b` |
| RTX 4070 / M1 Pro | `qwen3:14b` |
| 8GB VRAM / laptop | `qwen3:8b` |

**Embeddings locally:** `ollama pull nomic-embed-text` — 768 dimensions, matches Neo4j default.

**Hybrid tip:** Run local for simulation rounds (high-volume), route to a cloud model only for final report generation. Most users land here naturally.

### Environment Variables

All settings live in `.env` (copy from `.env.example`):

```bash
# LLM
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_NAME=qwen3.5:27b

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=miroshark

# Embeddings
EMBEDDING_PROVIDER=ollama          # "ollama" or "openai"
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_BASE_URL=http://localhost:11434
EMBEDDING_DIMENSIONS=768
```


---

## Hardware Requirements

**Local (Ollama):**

| | Minimum | Recommended |
|---|---|---|
| RAM | 16 GB | 32 GB |
| VRAM | 10 GB | 24 GB |
| Disk | 20 GB | 50 GB |

**Cloud mode:** No GPU needed — just Neo4j and an API key. Any 4 GB RAM machine works.

## Use Cases

- **PR crisis testing** — simulate public reaction to a press release before publishing
- **Trading signals** — feed financial news and observe simulated market sentiment
- **Policy analysis** — test draft regulations against a simulated public
- **Creative experiments** — feed a novel with a lost ending; agents write a narratively consistent conclusion

## License

AGPL-3.0. See [LICENSE](./LICENSE).

## Credits

Built on [MiroFish](https://github.com/666ghj/MiroFish) by [666ghj](https://github.com/666ghj), originally supported by [Shanda Group](https://www.shanda.com/).

The Neo4j + Ollama storage layer was adapted from [MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline) by [nikmcfly](https://github.com/nikmcfly) — the `GraphStorage` abstraction, Neo4j schema, embedding service, NER extractor, and hybrid search all originate there.

Simulation engine powered by **[OASIS](https://github.com/camel-ai/oasis)** from the CAMEL-AI team.
