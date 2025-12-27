# Podcast Search

**A searchable podcast knowledge engine that transforms any YouTube channel into a private, citation-backed ChatGPT.**

The core idea: take any YouTube channel with long-form podcast content, ingest the entire catalogue, and turn it into something you can actually search and talk to.

Under the hood, it downloads audio, transcribes with speaker diarization, breaks conversations into semantically meaningful chunks, and embeds everything. Once done, the whole channel becomes a structured knowledge base — search for ideas (not just keywords), filter by speaker or episode, jump to exact timestamps, or ask questions in natural language and get answers with citations.

**This isn't just "transcripts + embeddings."** It uses hybrid search (semantic + full-text), cross-encoder re-ranking, proper RAG with grounded citations, and supports multiple transcription backends that work at scale.

---

## Quick Start

```bash
# 1. Clone and configure
git clone <repo> && cd podcast-search
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys

# 2. Run everything
make up && make migrate

# 3. Open http://localhost:3000
```

**Required API Keys** (`backend/.env`):
```env
OPENAI_API_KEY=sk-...           # Embeddings (text-embedding-3-small, 1536 dims)
ANTHROPIC_API_KEY=sk-ant-...    # RAG chat (Claude 3.5 Sonnet)
ASSEMBLYAI_API_KEY=...          # Transcription (or DEEPGRAM_API_KEY)
ADMIN_SECRET=change-me          # Admin authentication
```

---

## How It Works: The AI Pipeline

### 1. Ingestion Pipeline

```
YouTube URL → yt-dlp → Audio (MP3) → Transcription API → Speaker Diarization
     │                                      │
     └──────────────────────────────────────┴──► Utterances with timestamps
```

- **Audio extraction**: yt-dlp extracts audio at optimal quality
- **Transcription**: 6 provider options with automatic failover
- **Speaker diarization**: Identifies who's speaking when (Speaker A, B, C...)
- **Speaker labeling**: Claude AI maps "Speaker A" → "Joe Rogan" using context clues

### 2. Chunking Strategy

```
Raw Utterances → Topic-Aware Chunking → Contextual Headers → Embeddings
```

**Why chunking matters**: LLMs have context limits. We need to break 3-hour podcasts into searchable pieces without losing meaning.

**Our approach**:
| Signal | Description |
|--------|-------------|
| **Speaker turns** | Break at speaker changes (natural conversation boundaries) |
| **Pause detection** | >2 second gaps indicate topic shifts |
| **Transition markers** | "Moving on...", "Let's talk about...", "Another question..." |
| **Target size** | ~500 words per chunk with 50-word overlap |

**Contextual chunk headers** (key innovation):
```
Episode: WTF Is Wealth with Ray Dalio
Channel: Nikhil Kamath
Date: December 2024
Speaker: Ray Dalio
---
The thing about compound interest is that most people underestimate
how powerful it becomes over 20-30 years...
```

This fixes the "lost context" problem where chunks like "He said the company was undervalued" become meaningless without knowing who "he" is or which company.

### 3. Embedding & Vector Search

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EMBEDDING PIPELINE                           │
├─────────────────────────────────────────────────────────────────────┤
│  Chunk Text  ──►  OpenAI text-embedding-3-small  ──►  1536-dim vector │
│                         │                                            │
│                    Cached in Redis                                   │
│                    (7-day TTL)                                       │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        VECTOR STORAGE                               │
├─────────────────────────────────────────────────────────────────────┤
│  Qdrant Vector DB                                                   │
│  ├── Collection: podcast_chunks                                     │
│  ├── Vectors: 1536 dimensions                                       │
│  ├── Payload: episode_id, speaker, timestamp, channel_id            │
│  └── Indexes: HNSW for fast ANN search                              │
└─────────────────────────────────────────────────────────────────────┘
```

**Model choice**: `text-embedding-3-small` (1536 dims)
- Best cost/performance ratio for RAG
- $0.02 per 1M tokens
- Outperforms ada-002 on retrieval benchmarks

### 4. Hybrid Search with Re-ranking

```
Query: "What does Ray Dalio think about diversification?"
                              │
        ┌─────────────────────┴─────────────────────┐
        ▼                                           ▼
┌───────────────────┐                   ┌───────────────────┐
│  SEMANTIC SEARCH  │                   │  KEYWORD SEARCH   │
│  (Qdrant vectors) │                   │  (PostgreSQL FTS) │
│                   │                   │                   │
│  "diversification │                   │  ts_query:        │
│   portfolio risk" │                   │  'ray' & 'dalio'  │
│   → cosine sim    │                   │  & 'diversif'     │
└─────────┬─────────┘                   └─────────┬─────────┘
          │                                       │
          └──────────────┬────────────────────────┘
                         ▼
              ┌─────────────────────┐
              │ RECIPROCAL RANK     │
              │ FUSION (RRF)        │
              │                     │
              │ score = Σ 1/(k+rank)│
              │ k=60, weights:      │
              │ semantic=0.7        │
              │ keyword=0.3         │
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │ MMR DIVERSITY       │
              │                     │
              │ Prevents 5 results  │
              │ from same minute    │
              │ of same episode     │
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │ CROSS-ENCODER       │
              │ RE-RANKING          │
              │                     │
              │ ms-marco-MiniLM-L6  │
              │ Top 50 → Top 10     │
              └──────────┬──────────┘
                         ▼
                  Final Results
```

**Why hybrid?** Semantic search finds conceptually similar content ("portfolio allocation" matches "diversification") while keyword search catches exact names and terms that embeddings might miss.

### 5. RAG Chat with Grounded Citations

```
┌─────────────────────────────────────────────────────────────────────┐
│                          RAG PIPELINE                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  User Question ──► Hybrid Search ──► Top 10 Chunks                  │
│                                            │                        │
│                                            ▼                        │
│                              ┌─────────────────────────┐            │
│                              │   CONTEXT WINDOW        │            │
│                              │                         │            │
│                              │   [Source 1]            │            │
│                              │   Episode: ...          │            │
│                              │   Speaker: Ray Dalio    │            │
│                              │   "Diversification is   │            │
│                              │   the only free lunch"  │            │
│                              │                         │            │
│                              │   [Source 2]            │            │
│                              │   ...                   │            │
│                              └───────────┬─────────────┘            │
│                                          │                          │
│                                          ▼                          │
│                              ┌─────────────────────────┐            │
│                              │   CLAUDE 3.5 SONNET     │            │
│                              │                         │            │
│                              │   System: Strict ground-│            │
│                              │   ing rules. Quote 5-15 │            │
│                              │   words for EVERY claim.│            │
│                              │   Never hallucinate.    │            │
│                              └───────────┬─────────────┘            │
│                                          │                          │
│                                          ▼                          │
│                              ┌─────────────────────────┐            │
│                              │   GROUNDED RESPONSE     │            │
│                              │                         │            │
│                              │   Ray Dalio emphasizes  │            │
│                              │   that "diversification │            │
│                              │   is the only free      │            │
│                              │   lunch in investing"[1]│            │
│                              │                         │            │
│                              │   Sources:              │            │
│                              │   [1] Ray Dalio, WTF Is │            │
│                              │       Wealth, 12:34     │            │
│                              └─────────────────────────┘            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Grounding rules** (prevents hallucination):
1. Every claim must include a 5-15 word quote from transcripts
2. Format: `"quoted text" [Source N]`
3. If context doesn't contain the answer, say so
4. Distinguish between what different speakers said

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (Next.js 14)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Search    │  │    Chat     │  │   Browse    │  │   Admin Dashboard   │ │
│  │   Page      │  │    Page     │  │   Podcasts  │  │   (Batches, Jobs)   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
└─────────┼────────────────┼────────────────┼────────────────────┼────────────┘
          │                │                │                    │
          └────────────────┴────────────────┴────────────────────┘
                                    │
                              HTTP / WebSocket
                                    │
┌───────────────────────────────────┼─────────────────────────────────────────┐
│                           BACKEND (FastAPI)                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         API LAYER                                    │   │
│  │  /api/search  /api/chat  /api/channels  /api/batches  /ws/updates   │   │
│  └─────────────────────────────────┬───────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────┴───────────────────────────────────┐   │
│  │                       SERVICE LAYER                                  │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ │   │
│  │  │HybridSearch  │ │ RAGService   │ │ Embedding    │ │ Chunking    │ │   │
│  │  │Service       │ │              │ │ Service      │ │ Service     │ │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └─────────────┘ │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ │   │
│  │  │ Reranker     │ │ Speaker      │ │ YouTube      │ │Transcription│ │   │
│  │  │ Service      │ │ Labeling     │ │ Service      │ │ Factory     │ │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └─────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────┴───────────────────────────────────┐   │
│  │                     INFRASTRUCTURE LAYER                             │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────────────┐ │   │
│  │  │ Circuit    │ │ Rate       │ │ Request ID │ │ Cache Service     │ │   │
│  │  │ Breakers   │ │ Limiter    │ │ Middleware │ │ (Redis)           │ │   │
│  │  └────────────┘ └────────────┘ └────────────┘ └───────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
          │                    │                    │                │
          ▼                    ▼                    ▼                ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐   ┌────────────┐
│  PostgreSQL  │     │    Qdrant    │     │    Redis     │   │   Celery   │
│              │     │              │     │              │   │            │
│ • Episodes   │     │ • Vectors    │     │ • Embedding  │   │ • Async    │
│ • Channels   │     │   1536-dim   │     │   cache      │   │   tasks    │
│ • Utterances │     │ • HNSW index │     │ • Search     │   │ • Batch    │
│ • Chunks     │     │ • Filters    │     │   cache      │   │   jobs     │
│ • GIN FTS    │     │              │     │ • Rate limit │   │            │
└──────────────┘     └──────────────┘     └──────────────┘   └────────────┘
```

---

## Performance Optimizations

| Optimization | Impact | Before → After |
|-------------|--------|----------------|
| **N+1 Query Fix** | Critical | 2N queries → 2 queries (batch loading) |
| **PostgreSQL FTS** | Critical | O(n) in-memory BM25 → O(log n) GIN index |
| **Embedding Cache** | High | API call every query → 7-day Redis TTL |
| **Search Cache** | Medium | Repeat searches → 5-minute TTL |
| **Connection Pooling** | High | New connection/request → Pool of 10 |
| **MMR Diversity** | Medium | 5 results from same minute → Diverse results |
| **Rerank Pool 50** | Medium | Top 30 reranked → Top 50 for better quality |
| **Circuit Breakers** | High | Cascading failures → Graceful degradation |

---

## Transcription Providers

| Provider | Speed | Cost | Diarization | Best For |
|----------|-------|------|-------------|----------|
| **AssemblyAI** | Cloud | $0.37/hr | ✅ Yes | Production accuracy |
| **Deepgram** | Cloud | $0.26/hr | ✅ Yes | Budget production |
| **Faster-Whisper** | 4x realtime | Free | ✅ Yes* | Self-hosted GPU |
| **Modal Cloud** | 70-200x | ~$0.03/hr | ❌ No | Batch processing |
| **OpenAI Whisper** | 1x realtime | Free | ❌ No | Simple local |

---

## Make Commands

```bash
make up           # Start all services (docker-compose up -d)
make down         # Stop all services
make logs         # View logs (docker-compose logs -f)
make test         # Run backend tests
make migrate      # Run database migrations
make shell        # Backend shell
make infra        # Start only postgres/redis/qdrant (for local dev)
make e2e-test     # Run full pipeline E2E test
make eval         # Run search quality evaluation
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Semantic Search** | Find content by meaning, not just keywords |
| **Hybrid Search** | Semantic + keyword + cross-encoder reranking |
| **RAG Chat** | Ask questions, get cited answers with timestamps |
| **Topic-Aware Chunking** | Breaks at speaker turns, pauses, topic shifts |
| **Speaker Labeling** | Claude AI identifies speakers from context |
| **6 Transcription Providers** | AssemblyAI, Deepgram, Whisper, Modal, etc. |
| **Real-time Updates** | WebSocket progress for batch transcription |
| **YouTube Integration** | Auto-fetch channels, metadata, thumbnails |
| **Admin Dashboard** | Manage channels, batches, jobs, view logs |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Next.js 14, TypeScript, Tailwind, shadcn/ui |
| **Backend** | FastAPI, Python 3.11, SQLAlchemy, Pydantic |
| **Vector DB** | Qdrant (HNSW index, 1536-dim vectors) |
| **Database** | PostgreSQL 16 (GIN indexes for FTS) |
| **Cache** | Redis 7 (embeddings, search, rate limiting) |
| **Task Queue** | Celery + Redis broker |
| **Embeddings** | OpenAI text-embedding-3-small |
| **LLM** | Claude 3.5 Sonnet (RAG), Claude Haiku (labeling) |
| **Reranker** | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| **Transcription** | AssemblyAI, Deepgram, Faster-Whisper, Modal |

---

## Development

```bash
# Run locally (requires infra running)
make infra
cd backend && pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm run dev

# Run tests with coverage
cd backend && pytest --cov=app --cov-report=html

# E2E test (full pipeline)
python tests/e2e/run_nikhil_kamath_test.py
```

---

## API Examples

```bash
# Search
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "startup advice", "limit": 10, "use_hybrid": true}'

# Chat with RAG
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What did they say about fundraising?"}'

# Add a YouTube channel
curl -X POST http://localhost:8000/api/channels \
  -H "Content-Type: application/json" \
  -H "X-Admin-Secret: your-secret" \
  -d '{"url": "https://youtube.com/@nikhil.kamath"}'
```

---

## License

MIT
