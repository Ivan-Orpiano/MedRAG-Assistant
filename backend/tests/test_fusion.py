from app.services.retrieval.fusion import (
    RetrievedChunk,
    is_grounded,
    lightweight_rerank,
    reciprocal_rank_fusion,
)


def make(cid, dense=0.0, kw=0.0, text="lorem ipsum"):
    return RetrievedChunk(
        chunk_id=cid, document_id="d", document_title="Doc", version_number=1,
        text=text, page_number=None, section=None, dense_score=dense, keyword_rank=kw,
    )


def test_rrf_prefers_chunks_present_in_both_lists():
    dense = [make("a", dense=0.9), make("b", dense=0.8), make("c", dense=0.7)]
    keyword = [make("b", kw=0.5), make("x", kw=0.4)]
    fused = reciprocal_rank_fusion(dense, keyword, top_n=4)
    assert fused[0].chunk_id == "b"
    assert fused[0].sources == {"dense", "keyword"}


def test_rrf_caps_top_n():
    dense = [make(str(i), dense=1 - i * 0.01) for i in range(20)]
    fused = reciprocal_rank_fusion(dense, [], top_n=5)
    assert len(fused) == 5


def test_grounding_gate_refuses_when_all_scores_low():
    chunks = [make("a", dense=0.10), make("b", kw=0.01)]
    assert not is_grounded(chunks, min_dense_score=0.28, min_keyword_rank=0.05)


def test_grounding_gate_passes_on_dense_or_keyword():
    assert is_grounded([make("a", dense=0.31)], 0.28, 0.05)
    assert is_grounded([make("a", kw=0.2)], 0.28, 0.05)
    assert not is_grounded([], 0.28, 0.05)


def test_lightweight_rerank_boosts_lexical_overlap():
    a = make("a", text="unrelated content entirely")
    b = make("b", text="metformin contraindications renal impairment egfr threshold")
    a.fused_score = 0.0165
    b.fused_score = 0.0160  # slightly behind before rerank
    ranked = lightweight_rerank([a, b], "metformin contraindications renal impairment")
    assert ranked[0].chunk_id == "b"
