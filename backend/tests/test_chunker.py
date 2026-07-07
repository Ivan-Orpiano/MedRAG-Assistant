from app.services.ingestion.chunker import chunk_pages, clean_text, count_tokens


def test_clean_text_normalizes_whitespace():
    assert clean_text("a\r\nb\t\tc\n\n\n\nd") == "a\nb c\n\nd"


def test_chunks_respect_target_size():
    para = "Sentence about hypertension management. " * 40
    pages = [(i, para) for i in range(1, 6)]
    chunks = chunk_pages(pages, target_tokens=200, overlap_ratio=0.15)
    assert len(chunks) > 1
    for c in chunks:
        assert count_tokens(c.text) <= 200 * 1.5  # some slack for paragraph granularity


def test_page_numbers_carried_through():
    pages = [(1, "First page content about aspirin." * 10), (2, "Second page content about statins." * 10)]
    chunks = chunk_pages(pages, target_tokens=60)
    assert chunks[0].page_number == 1
    assert any(c.page_number == 2 for c in chunks)


def test_headings_become_sections():
    text = "CONTRAINDICATIONS AND WARNINGS\n\nDo not administer to patients with renal failure."
    chunks = chunk_pages([(1, text)], target_tokens=500)
    assert chunks[0].section is not None
    assert "CONTRAINDICATIONS" in chunks[0].section


def test_overlap_preserves_boundary_content():
    paras = "\n\n".join(f"Paragraph number {i} discussing dosage details." for i in range(30))
    chunks = chunk_pages([(None, paras)], target_tokens=80, overlap_ratio=0.3)
    assert len(chunks) >= 2
    # tail of chunk N should reappear at head of chunk N+1
    tail = chunks[0].text.split("\n\n")[-1]
    assert tail in chunks[1].text
