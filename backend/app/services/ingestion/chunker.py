"""Structure-aware chunking.

Paragraphs (and heading-delimited sections) are packed into chunks of roughly
CHUNK_TARGET_TOKENS with ~15% overlap so facts split across a boundary survive
in at least one chunk. Page numbers and the nearest heading are carried as
metadata so every chunk is independently citable."""
import re
from dataclasses import dataclass

try:
    import tiktoken

    _enc = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))
except Exception:  # pragma: no cover - offline fallback

    def count_tokens(text: str) -> int:
        return max(1, len(text) // 4)


_HEADING_RE = re.compile(r"^(#{1,6}\s+.+|[A-Z][A-Z0-9 \-/:,()]{6,80})$")
_WS_RE = re.compile(r"[ \t]+")


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@dataclass
class ChunkPiece:
    text: str
    page_number: int | None
    section: str | None
    chunk_index: int


def _split_paragraphs(pages: list[tuple[int | None, str]]) -> list[tuple[str, int | None, str | None]]:
    """Yield (paragraph, page_number, current_section) tuples."""
    out: list[tuple[str, int | None, str | None]] = []
    section: str | None = None
    for page_no, text in pages:
        for para in clean_text(text).split("\n\n"):
            para = para.strip()
            if not para:
                continue
            first_line = para.split("\n", 1)[0].strip()
            if _HEADING_RE.match(first_line) and len(first_line) < 120:
                section = first_line.lstrip("# ").strip()
            out.append((para, page_no, section))
    return out


def chunk_pages(
    pages: list[tuple[int | None, str]],
    target_tokens: int = 800,
    overlap_ratio: float = 0.15,
) -> list[ChunkPiece]:
    paragraphs = _split_paragraphs(pages)
    chunks: list[ChunkPiece] = []
    buf: list[tuple[str, int | None, str | None]] = []
    buf_tokens = 0
    overlap_tokens = int(target_tokens * overlap_ratio)

    def flush() -> None:
        nonlocal buf, buf_tokens
        if not buf:
            return
        text = "\n\n".join(p for p, _, _ in buf)
        page = next((pg for _, pg, _ in buf if pg is not None), None)
        section = next((s for _, _, s in buf if s), None)
        chunks.append(ChunkPiece(text=text, page_number=page, section=section, chunk_index=len(chunks)))
        # carry tail paragraphs forward as overlap
        kept: list[tuple[str, int | None, str | None]] = []
        kept_tokens = 0
        for item in reversed(buf):
            t = count_tokens(item[0])
            if kept_tokens + t > overlap_tokens:
                break
            kept.insert(0, item)
            kept_tokens += t
        buf = kept
        buf_tokens = kept_tokens

    for para, page_no, section in paragraphs:
        t = count_tokens(para)
        if t > target_tokens:  # single oversized paragraph: hard-split by sentences
            for piece in re.split(r"(?<=[.!?])\s+", para):
                pt = count_tokens(piece)
                if buf_tokens + pt > target_tokens:
                    flush()
                buf.append((piece, page_no, section))
                buf_tokens += pt
            continue
        if buf_tokens + t > target_tokens:
            flush()
        buf.append((para, page_no, section))
        buf_tokens += t

    if buf and (not chunks or buf_tokens > overlap_tokens):
        text = "\n\n".join(p for p, _, _ in buf)
        page = next((pg for _, pg, _ in buf if pg is not None), None)
        section = next((s for _, _, s in buf if s), None)
        chunks.append(ChunkPiece(text=text, page_number=page, section=section, chunk_index=len(chunks)))
    return chunks
