"""Hybrid retrieval orchestrator: query rewrite -> dense + keyword search in
parallel semantics -> RRF -> lightweight rerank -> grounding gate."""
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.schemas import RetrievalFilters
from app.services.embeddings import embed_query
from app.services.retrieval import keyword, vector_store
from app.services.retrieval.fusion import (
    RetrievedChunk,
    is_grounded,
    lightweight_rerank,
    reciprocal_rank_fusion,
)

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    grounded: bool
    rewritten_query: str


def retrieve(
    db: Session,
    query: str,
    filters: RetrievalFilters | None = None,
    top_k: int | None = None,
) -> RetrievalResult:
    settings = get_settings()
    top_k = top_k or settings.retrieval_top_k
    candidates = settings.retrieval_candidates

    doc_ids = [str(i) for i in filters.document_ids] if filters and filters.document_ids else None
    categories = [c.value for c in filters.categories] if filters and filters.categories else None
    tags = filters.tags if filters else None
    after_ts = filters.uploaded_after.timestamp() if filters and filters.uploaded_after else None
    before_ts = filters.uploaded_before.timestamp() if filters and filters.uploaded_before else None

    # --- dense ---
    vector = embed_query(query)
    qfilter = vector_store.build_filter(doc_ids, categories, tags, after_ts, before_ts)
    dense_hits = vector_store.dense_search(vector, candidates, qfilter)
    dense_chunks = [
        RetrievedChunk(
            chunk_id=str(hit.id),
            document_id=hit.payload["document_id"],
            document_title=hit.payload["document_title"],
            version_number=hit.payload["version_number"],
            text=hit.payload["text"],
            page_number=hit.payload.get("page_number"),
            section=hit.payload.get("section"),
            dense_score=float(hit.score),
        )
        for hit in dense_hits
    ]

    # --- keyword (sparse) ---
    kw_rows = keyword.keyword_search(
        db,
        query,
        candidates,
        document_ids=[uuid.UUID(i) for i in doc_ids] if doc_ids else None,
        categories=categories,
        tags=tags,
    )
    keyword_chunks = [
        RetrievedChunk(
            chunk_id=str(r["id"]),
            document_id=str(r["document_id"]),
            document_title=r["document_title"],
            version_number=r["version_number"],
            text=r["text"],
            page_number=r["page_number"],
            section=r["section"],
            keyword_rank=float(r["rank"]),
        )
        for r in kw_rows
    ]

    fused = reciprocal_rank_fusion(dense_chunks, keyword_chunks, top_n=top_k)
    fused = lightweight_rerank(fused, query)
    grounded = is_grounded(fused, settings.min_dense_score, settings.min_keyword_rank)
    logger.info(
        "retrieval",
        extra={
            "extra_fields": {
                "grounded": grounded,
                "dense_hits": len(dense_chunks),
                "keyword_hits": len(keyword_chunks),
                "fused": len(fused),
                "top_dense_score": max((c.dense_score for c in fused), default=0.0),
            }
        },
    )
    return RetrievalResult(chunks=fused, grounded=grounded, rewritten_query=query)
