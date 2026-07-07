# MedAssist — AI Medical Knowledge Assistant (RAG)

**For educational and research purposes only.** This system does not replace professional medical judgment and must not be used to diagnose or treat patients. Every answer is generated strictly from the uploaded document corpus and carries citations for verification. The disclaimer is displayed on every page of the UI, on the login screen, in the API's OpenAPI description, and in the `/health` endpoint.

A production-oriented Retrieval-Augmented Generation system for healthcare professionals and researchers, built on a **fully Python stack** — FastAPI backend and NiceGUI frontend (no JavaScript, no TypeScript, no Tailwind).

## Architecture

```
                       ┌──────────────────────────────────────────────┐
  Browser ──WebSocket──►  NiceGUI frontend (pure Python, port 8080)   │
                       └───────────────┬──────────────────────────────┘
                                       │ HTTP + SSE (JWT bearer)
                       ┌───────────────▼──────────────────────────────┐
                       │  FastAPI (port 8000)                         │
                       │  auth · documents · chat · admin             │
                       └───┬─────────┬─────────┬─────────┬────────────┘
                           │         │         │         │
                     PostgreSQL   Qdrant     Redis     Celery worker
                     (metadata,  (dense    (cache,    (ingestion:
                      chunks +    vectors)  rate       extract→OCR→
                      tsvector)             limits,    chunk→embed→
                                            broker)    index)
                           │                              │
                           └────────── Object storage ────┘
                                (local FS / S3 / Supabase Storage)
```

**Hybrid retrieval.** Dense semantic search (OpenAI `text-embedding-3-large` in Qdrant) and keyword search (PostgreSQL `tsvector` with a GIN index) run over the same chunks — the Qdrant point id equals the Postgres chunk id — and are fused with Reciprocal Rank Fusion. Dense catches paraphrase; keyword catches exact drug names, codes, and acronyms that vectors miss.

**Grounding is structural, not a prompt suggestion.** After fusion, a grounding gate checks whether any candidate clears a dense-similarity or keyword-rank threshold (`MIN_DENSE_SCORE`, `MIN_KEYWORD_RANK`). If nothing clears the bar, **the LLM is never called** and the fixed "documents do not contain enough information" message is returned. Hallucinating from an empty context is architecturally impossible. On the grounded path, the system prompt additionally enforces citation markers, verbatim numeric values, and explicit surfacing of conflicting sources.

**Multi-turn grounding.** Follow-up questions ("what about its contraindications?") are rewritten into self-contained search queries using conversation history before retrieval, so retrieval never runs on an unresolved pronoun.

**Citations.** Every grounded answer streams inline `[n]` markers; after generation, only the markers actually used are resolved into citation objects carrying document title, version, page number (when available), section, relevance score, and a verbatim excerpt.

## Roles (RBAC)

| Capability | Administrator | Doctor | Researcher |
|---|---|---|---|
| Ask questions, view own chat history | ✅ | ✅ | ✅ |
| Upload documents / new versions, edit metadata | ✅ | ✅ | ✅ |
| Delete documents | ✅ | — | — |
| Re-trigger indexing | ✅ | — | — |
| Manage users, view admin dashboard | ✅ | — | — |

## Quick start

```bash
cp .env.example .env      # set OPENAI_API_KEY, SECRET_KEY, FIRST_ADMIN_* at minimum
docker compose up -d --build
docker compose exec api python -m app.bootstrap   # create the first admin (idempotent)
```

- Frontend: http://localhost:8080 (log in with `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD`)
- API docs (OpenAPI/Swagger): http://localhost:8000/docs

Migrations run automatically via the `migrate` service (`alembic upgrade head`) before the API and worker start. To create a new migration after changing models: `docker compose run --rm api alembic revision --autogenerate -m "describe change"`.

## Ingestion pipeline

Upload (PDF/DOCX/TXT, ≤50 MB) → stored in object storage → Celery task: extract text per page (`pypdf`; pages with an empty text layer are rasterized at 300 dpi and OCR'd with Tesseract) → clean → structure-aware chunking (~800 tokens, 15% paragraph overlap, headings become section metadata) → batched embeddings → upsert to Qdrant + Postgres, `tsvector` populated → version marked `indexed`. Re-runs are idempotent (previous vectors/chunks for the version are replaced). Uploading a new version supersedes the old one so retrieval only ever sees the latest indexed version. Deleting a document is a soft delete followed by an async purge of vectors, chunks, and stored files.

## Metadata filtering

The chat page exposes filters that constrain retrieval **before** search: category, specific documents, tags, upload date range, and top-k. These map to Qdrant payload filters and SQL predicates respectively, so both halves of hybrid search honor them.

## Evaluation harness

Retrieval and generation are evaluated separately (`eval/run_eval.py`):

```bash
docker compose exec api python -m eval.run_eval --file eval/eval_set.example.jsonl --k 8            # retrieval recall + refusal accuracy (no LLM cost)
docker compose exec api python -m eval.run_eval --file my_eval.jsonl --generate --judge             # + answer content checks + LLM-judge faithfulness
```

Metrics: retrieval recall@k, refusal accuracy on out-of-corpus questions (does the grounding gate correctly say "I don't know"?), expected-content hits, and binary LLM-judge faithfulness. Failures are printed as transcripts — read them; the score only tells you *whether*, the transcripts tell you *why*. Grow the eval set from real failures.

## Testing

```bash
cd backend && pip install -r requirements.txt && pytest tests/ -q
```

20 unit tests cover chunking (size, overlap, page/section metadata), RRF fusion, the grounding gate, rerank behavior, citation resolution, context assembly, extraction, and auth primitives.

## Operations

- **Rate limiting** — Redis fixed-window per user: chat 30/min, uploads 20/h, default 240/min (configurable).
- **Caching** — query embeddings cached in Redis 24h, keyed by model+dimensions+normalized query.
- **Logging** — structured JSON to stdout everywhere; retrieval logs grounded/hit counts per query for observability.
- **Monitoring** — admin dashboard shows corpus size, indexing queue with per-version status/errors/OCR counts, grounded-vs-refused answer counts, average latency, and 7-day usage events.

## Known limitations (deliberate, with designed swap points)

1. **Lightweight reranker.** RRF + lexical-overlap boost, not a cross-encoder. `lightweight_rerank()` in `app/services/retrieval/fusion.py` is the swap point — replacing it with a hosted reranker (Cohere Rerank, BGE) is the single biggest quality lift available.
2. **Grounding thresholds need calibration.** `MIN_DENSE_SCORE=0.28` is a sane starting point for `text-embedding-3-large`, but the right value depends on your corpus. Use the eval harness's refusal-accuracy metric to tune it.
3. **Sync SQLAlchemy.** Shared session code between FastAPI (threadpool) and Celery keeps the codebase simple; at high concurrency, migrating the API to async sessions is the next step.
4. **Single-tenant.** No org/workspace isolation; all users share one corpus (filterable, not partitioned).
