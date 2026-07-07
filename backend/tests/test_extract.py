from app.services.ingestion.extract import SUPPORTED_MIME, extract


def test_txt_extraction():
    result = extract("Hello clinical world".encode(), "text/plain")
    assert result.page_count == 1
    assert result.pages[0].text == "Hello clinical world"
    assert result.ocr_pages == 0


def test_unsupported_mime_raises():
    import pytest

    with pytest.raises(ValueError):
        extract(b"...", "image/png")


def test_supported_mime_map_covers_requirements():
    assert "application/pdf" in SUPPORTED_MIME
    assert "text/plain" in SUPPORTED_MIME
    assert any("wordprocessingml" in m for m in SUPPORTED_MIME)
