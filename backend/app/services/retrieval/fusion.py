"""Reciprocal Rank Fusion of dense and keyword result lists, plus the
grounding decision that gates whether the LLM is called at all."""
from dataclasses import dataclass, field


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_title: str
    version_number: int
    text: str
    page_number: int | None
    section: str | None
    dense_score: float = 0.0
    keyword_rank: float = 0.0
    fused_score: float = 0.0
    sources: set = field(default_factory=set)


def reciprocal_rank_fusion(
    dense: list[RetrievedChunk],
    keyword: list[RetrievedChunk],
    k: int = 60,
    top_n: int = 8,
) -> list[RetrievedChunk]:
    by_id: dict[str, RetrievedChunk] = {}
    for rank, chunk in enumerate(dense):
        item = by_id.setdefault(chunk.chunk_id, chunk)
        item.dense_score = max(item.dense_score, chunk.dense_score)
        item.fused_score += 1.0 / (k + rank + 1)
        item.sources.add("dense")
    for rank, chunk in enumerate(keyword):
        item = by_id.setdefault(chunk.chunk_id, chunk)
        item.keyword_rank = max(item.keyword_rank, chunk.keyword_rank)
        item.fused_score += 1.0 / (k + rank + 1)
        item.sources.add("keyword")
    ranked = sorted(by_id.values(), key=lambda c: c.fused_score, reverse=True)
    return ranked[:top_n]


def is_grounded(
    chunks: list[RetrievedChunk],
    min_dense_score: float,
    min_keyword_rank: float,
) -> bool:
    """The anti-hallucination gate.

    If no candidate clears either relevance bar, the corpus does not contain
    the answer and the LLM call never fires — refusal is structural, not a
    prompt suggestion.
    """
    return any(
        c.dense_score >= min_dense_score or c.keyword_rank >= min_keyword_rank
        for c in chunks
    )


def lightweight_rerank(chunks: list[RetrievedChunk], query: str) -> list[RetrievedChunk]:
    """Cheap lexical-overlap boost on top of RRF.

    Deliberate swap point: replace this function with a hosted cross-encoder
    (e.g. Cohere Rerank or a BGE reranker service) for the single biggest
    quality lift available to this pipeline. The signature is the contract.
    """
    query_terms = {t for t in query.lower().split() if len(t) > 3}
    if not query_terms:
        return chunks

    def overlap(c: RetrievedChunk) -> float:
        text_terms = set(c.text.lower().split())
        return len(query_terms & text_terms) / len(query_terms)

    return sorted(chunks, key=lambda c: c.fused_score + 0.1 * overlap(c), reverse=True)
