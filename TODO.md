# Podcast Search - Comprehensive TODO List

## Legend
- `[P0]` Critical - Must fix
- `[P1]` High - Should do soon
- `[P2]` Medium - Nice to have
- `[P3]` Low - Future enhancement

---

## BACKEND - RAG & Search Improvements

### 1. Chunking Strategy (Biggest Real-World Lever) `[P0]`

Current: Fixed ~500 word chunks with speaker-aware breaks
Issues: Podcasts aren't documents - topic drift + pronouns kill retrieval

- [ ] **Implement topic-shift detection** - Break on phrases like "anyway", "moving on", "let's talk about"
- [ ] **Add pause/timestamp-based chunking** - Long pauses (>3s) indicate topic shifts
- [ ] **Parent-child chunking** - Small chunks for retrieval, larger parent for RAG context
  - Small chunks: ~200 words for precise matching
  - Parent context: ~1000 words for complete answers
- [ ] **Semantic similarity chunking** - Use embeddings to detect topic boundaries
- [ ] **Store chunk hierarchy in DB** - Add `parent_chunk_id` to Chunk model

### 2. Contextual Chunk Headers (Easy, High ROI) `[P0]`

Current: Chunks stored as plain text
Fix: Prepend metadata before embedding

- [ ] **Add chunk header enrichment** in `chunking.py`:
  ```
  Episode: <title>
  Channel: <podcast name>
  Date: <month/year>
  Speaker: <speaker name>
  ---
  <chunk text>
  ```
- [ ] **Update embedding service** to use enriched text for vectors
- [ ] **Store both raw and enriched text** - raw for display, enriched for search

### 3. HyPE-lite Indexing (Question-First Retrieval) `[P1]`

Current: Only chunk embeddings stored
Add: Hypothetical question embeddings

- [ ] **Generate hypothetical questions at index time**
  - 2-3 questions per chunk using Claude
  - "What would someone ask to find this content?"
- [ ] **Store question embeddings alongside chunk embeddings**
- [ ] **Query matches both** chunk embeddings OR question embeddings
- [ ] **Map results back to original chunks**

### 4. Dynamic Hybrid Search Routing `[P1]`

Current: Fixed 0.7 semantic / 0.3 keyword weights
Improve: Dynamic weighting based on query type

- [ ] **Implement query classifier**
  - Named entities / titles → keyword-heavy (0.3/0.7)
  - Conceptual questions → vector-heavy (0.8/0.2)
  - Quotes → exact match first
- [ ] **Add query intent detection** using Claude or rule-based
- [ ] **Add MMR (Maximal Marginal Relevance)** to prevent 5 chunks from same minute

### 5. Aggressive Reranking `[P1]`

Current: Rerank top 30 (limit * 3)
Improve: Rerank more, use confidence thresholds

- [ ] **Increase rerank pool** to top 50-100 candidates
- [ ] **Add confidence thresholds**
  - If reranker scores are weak → answer cautiously
  - Add "low confidence" flag to response
- [ ] **Speaker-aware reranking** when filters are used
- [ ] **Cache reranker results** for common queries

### 6. Relevant Segment Extraction (RSE) `[P1]`

Current: Return individual chunks
Improve: Expand to contiguous conversation segments

- [ ] **Implement segment expansion** in search enrichment
  - After retrieval, expand top chunks into contiguous segments
  - Cap by token budget (e.g., 2000 tokens)
- [ ] **Feed segments to RAG** not isolated chunks
- [ ] **Store segment boundaries** for display

### 7. RAG Grounding & Citations `[P0]`

Current: Basic citation format
Improve: Strict grounding, quoted spans

- [ ] **Enforce strict grounding** - "Answer ONLY from retrieved text"
- [ ] **Require quoted spans** (5-15 words) for each claim
- [ ] **Add confidence scoring** - If retrieval weak, say so
- [ ] **Suggest better queries** when confidence is low
- [ ] **Add inline citations** format: `"quoted text" [1]`

### 8. Embeddings Improvements `[P2]`

Current: text-embedding-3-small, 1536 dims
Consider: Dimensionality reduction for cost

- [ ] **Evaluate reduced dimensions** (e.g., 512 or 256)
  - OpenAI supports native dimension reduction
  - Test retrieval quality vs cost savings
- [ ] **Add batch embedding optimization** - Current is good, verify batching
- [ ] **Consider text-embedding-3-large** for higher quality (test cost/benefit)

### 9. Evaluation Framework `[P0]`

Current: No systematic evaluation
Add: Proper measurement before optimizing

- [ ] **Create golden test set** - 50-100 real queries with relevant chunks marked
- [ ] **Track metrics**:
  - Recall@50
  - nDCG@10
  - Citation faithfulness
  - Answer relevance (LLM-as-judge)
- [ ] **Add A/B testing framework** for search changes
- [ ] **Log search quality signals** for analysis

---

## BACKEND - Transcription Providers

### 10. Multi-Provider Support `[P1]`

Available providers: AssemblyAI, Deepgram, Whisper, Faster-Whisper, Modal

- [ ] **Add provider fallback chain** - If one fails, try next
- [ ] **Add cost-aware routing** - Route based on audio length/budget
- [ ] **Fix Deepgram API key** in .env (currently empty)
- [ ] **Test Faster-Whisper** for local/free transcription
- [ ] **Add provider health checks** in detailed health endpoint

### 11. Transcription Quality `[P2]`

- [ ] **Add confidence threshold** - Flag low-confidence transcriptions
- [ ] **Implement retry with different provider** for poor quality
- [ ] **Add audio quality detection** - Skip/warn for poor audio

---

## BACKEND - Performance & Infrastructure

### 12. Database Optimizations `[P1]`

- [ ] **Add composite indexes** for common query patterns
- [ ] **Implement connection pooling monitoring**
- [ ] **Add query performance logging** (slow query alerts)
- [ ] **Partition chunks table** by channel for large datasets

### 13. Caching Improvements `[P2]`

- [ ] **Cache hypothetical questions** (when implemented)
- [ ] **Add cache warming** for popular channels
- [ ] **Implement cache invalidation** on content updates

### 14. Background Job Improvements `[P2]`

- [ ] **Add job progress tracking** with WebSocket updates
- [ ] **Implement job cancellation**
- [ ] **Add retry with backoff** for failed jobs
- [ ] **Dead letter queue** for permanently failed jobs

---

## BACKEND - Code Cleanup `[P2]`

- [ ] **Remove duplicate code** in hybrid_search.py and search.py
  - `_enrich_result` duplicated - use SearchEnrichmentService everywhere
  - `_get_context_utterances` duplicated
- [ ] **Consolidate search services** - Too many overlapping classes
- [ ] **Remove unused imports** across all files
- [ ] **Add type hints** to all function signatures
- [ ] **Standardize error handling** patterns

---

## BACKEND - Tests `[P0]`

### Unit Tests
- [ ] **Chunking service tests** - Various transcript shapes
- [ ] **Embedding service tests** - Batching, error handling
- [ ] **Search service tests** - Filters, scoring
- [ ] **RAG service tests** - Context building, citations

### Integration Tests
- [ ] **Full pipeline tests** - YouTube → transcribe → chunk → embed → search
- [ ] **Provider tests** - Each transcription provider
- [ ] **Cache tests** - Hit/miss scenarios

### E2E Tests
- [ ] **Search quality tests** - Against golden set
- [ ] **Chat quality tests** - Answer accuracy
- [ ] **Performance tests** - Latency benchmarks

---

## FRONTEND - Design & UX `[P1]`

### Icons & Visual Elements
- [ ] **Add Lucide icons throughout**:
  - `Mic` / `Headphones` for podcast branding
  - `MessageSquare` for chat
  - `Sparkles` for AI features
  - `Waveform` for audio visualization
  - `BookOpen` for transcripts
  - `Quote` for citations
  - `Play` for timestamp links
  - `Filter` for search filters
  - `TrendingUp` for popular/trending
  - `History` for recent searches

### Search Page Improvements
- [ ] **Add search suggestions** dropdown
- [ ] **Add recent searches** with `History` icon
- [ ] **Add popular queries** section
- [ ] **Visual loading skeleton** instead of spinner
- [ ] **Add waveform visualization** for audio results
- [ ] **Highlight speaker names** with distinct colors
- [ ] **Add "Powered by AI" badge** with `Sparkles`

### Result Cards
- [ ] **Add play button overlay** on thumbnails
- [ ] **Add share button** for each result
- [ ] **Add "similar results"** accordion
- [ ] **Visual confidence indicator** (meter/bar)
- [ ] **Add speaker avatar placeholders**

### Chat Interface
- [ ] **Add typing indicator** animation
- [ ] **Citation hover previews**
- [ ] **Add copy button** for answers
- [ ] **Add thumbs up/down** for feedback
- [ ] **Add regenerate button**
- [ ] **Source panel** showing all citations

### General UI
- [ ] **Add dark mode toggle** with `Moon`/`Sun` icons
- [ ] **Add loading states** everywhere
- [ ] **Add empty states** with illustrations
- [ ] **Add error states** with retry buttons
- [ ] **Improve mobile responsiveness**

---

## FRONTEND - Functionality `[P2]`

- [ ] **Add search history** (localStorage)
- [ ] **Add bookmarks/favorites**
- [ ] **Add share functionality**
- [ ] **Add keyboard shortcuts** (Cmd+K for search)
- [ ] **Add PWA support**
- [ ] **Add offline mode** for cached results

---

## FRONTEND - Performance `[P2]`

- [ ] **Add React Query** for caching/deduplication
- [ ] **Implement virtual scrolling** for long result lists
- [ ] **Add prefetching** for likely next pages
- [ ] **Optimize images** with next/image blur placeholders
- [ ] **Add web vitals monitoring**

---

## FRONTEND - Tests `[P1]`

- [ ] **Component tests** - Jest/Vitest + React Testing Library
- [ ] **E2E tests** - Playwright for critical flows
- [ ] **Visual regression tests** - Chromatic/Percy
- [ ] **Accessibility tests** - axe-core integration

---

## INFRASTRUCTURE `[P3]`

- [ ] **Add Sentry** for error tracking
- [ ] **Add structured logging** (JSON format)
- [ ] **Add metrics** (Prometheus/Grafana)
- [ ] **Add health dashboards**
- [ ] **Add alerting** for failures
- [ ] **Add load testing** scripts

---

## DOCUMENTATION `[P3]`

- [ ] **API documentation** - OpenAPI/Swagger (already have /docs)
- [ ] **Architecture diagram** - Mermaid in README
- [ ] **Deployment guide**
- [ ] **Contributing guide**
- [ ] **Search quality tuning guide**

---

## Priority Order for Implementation

### Phase 1 - Foundation (Now)
1. Evaluation framework (can't improve what you can't measure)
2. Contextual chunk headers (easy win)
3. RAG grounding improvements
4. Basic FE icons & polish

### Phase 2 - Search Quality
5. Topic-aware chunking
6. Dynamic hybrid search routing
7. HyPE-lite indexing
8. Aggressive reranking

### Phase 3 - UX Polish
9. FE design overhaul
10. Chat improvements
11. Performance optimizations

### Phase 4 - Scale
12. Multi-provider transcription
13. Infrastructure monitoring
14. Load testing & optimization

---

## Notes from Reddit RAG Best Practices

> "Chunking strategy matters more than the embedding model"

> "Podcasts aren't documents - topic drift + pronouns kill retrieval"

> "Reranking is where relevance really gets fixed"

> "Answers improve when you show conversation, not snippets"

> "Hallucinations are a retrieval + prompting problem"

> "Measure before optimizing"
