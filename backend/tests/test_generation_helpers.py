from app.services.generation import build_context_block, citations_from_chunks
from app.services.retrieval.fusion import RetrievedChunk


def make(cid, title, page=None, text="Aspirin 81mg daily."):
    return RetrievedChunk(
        chunk_id=cid, document_id="d1", document_title=title, version_number=2,
        text=text, page_number=page, section="Dosing", dense_score=0.5,
    )


def test_context_block_is_numbered_and_attributed():
    block = build_context_block([make("a", "Cardiology SOP", page=4)])
    assert block.startswith("[1] From \"Cardiology SOP\" (v2, page 4)")
    assert "Aspirin 81mg" in block


def test_citations_only_for_used_markers():
    chunks = [make("a", "Doc A"), make("b", "Doc B"), make("c", "Doc C")]
    answer = "The recommended dose is 81mg [1]. Contraindicated in ulcer disease [3]."
    citations = citations_from_chunks(chunks, answer)
    assert [c["marker"] for c in citations] == [1, 3]


def test_citations_fall_back_to_all_chunks_when_no_markers():
    chunks = [make("a", "Doc A"), make("b", "Doc B")]
    citations = citations_from_chunks(chunks, "An answer without markers.")
    assert [c["marker"] for c in citations] == [1, 2]
    assert citations[0]["document_title"] == "Doc A"
