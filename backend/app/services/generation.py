"""Grounded answer generation with token streaming.

Flow per question:
  1. Rewrite the query using conversation history (multi-turn grounding).
  2. Hybrid retrieval + grounding gate.
  3. If NOT grounded: return the fixed unavailability message — no LLM call.
  4. If grounded: stream the answer with inline [n] citation markers, then emit
     the resolved citation objects.
"""
from collections.abc import Iterator
from pathlib import Path

from openai import OpenAI

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.retrieval.fusion import RetrievedChunk

logger = get_logger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
GROUNDED_SYSTEM_PROMPT = (_PROMPT_DIR / "grounded_answer.txt").read_text()
QUERY_REWRITE_PROMPT = (_PROMPT_DIR / "query_rewrite.txt").read_text()

NOT_FOUND_MESSAGE = (
    "The uploaded documents do not contain enough information to answer this "
    "question. Please refine the question or upload relevant source material."
)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=get_settings().openai_api_key)
    return _client


def rewrite_query(question: str, history: list[dict]) -> str:
    """Turn 'what about its contraindications?' into a self-contained query."""
    if not history:
        return question
    recent = history[-6:]
    convo = "\n".join(f"{m['role']}: {m['content'][:500]}" for m in recent)
    try:
        response = _get_client().chat.completions.create(
            model=get_settings().openai_chat_model,
            messages=[
                {"role": "system", "content": QUERY_REWRITE_PROMPT},
                {"role": "user", "content": f"History:\n{convo}\n\nLatest question: {question}"},
            ],
            temperature=0.0,
            max_tokens=200,
        )
        rewritten = (response.choices[0].message.content or "").strip()
        return rewritten or question
    except Exception:
        logger.exception("query rewrite failed; falling back to raw question")
        return question


def build_context_block(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        page = f", page {c.page_number}" if c.page_number else ""
        section = f" > {c.section}" if c.section else ""
        parts.append(f"[{i}] From \"{c.document_title}\" (v{c.version_number}{page}){section}:\n{c.text}")
    return "\n\n---\n\n".join(parts)


def stream_grounded_answer(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[dict],
) -> Iterator[str]:
    settings = get_settings()
    context = build_context_block(chunks)
    messages = [{"role": "system", "content": GROUNDED_SYSTEM_PROMPT}]
    for m in history[-6:]:
        messages.append({"role": m["role"], "content": m["content"][:2000]})
    messages.append(
        {
            "role": "user",
            "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}",
        }
    )
    stream = _get_client().chat.completions.create(
        model=settings.openai_chat_model,
        messages=messages,
        temperature=0.1,
        stream=True,
    )
    for event in stream:
        delta = event.choices[0].delta.content if event.choices else None
        if delta:
            yield delta


def citations_from_chunks(chunks: list[RetrievedChunk], answer_text: str) -> list[dict]:
    """Return citation objects for markers actually used in the answer.
    Falls back to all retrieved chunks if the model produced no markers."""
    used = {i for i in range(1, len(chunks) + 1) if f"[{i}]" in answer_text}
    indices = sorted(used) if used else list(range(1, len(chunks) + 1))
    citations = []
    for i in indices:
        c = chunks[i - 1]
        citations.append(
            {
                "marker": i,
                "document_id": c.document_id,
                "document_title": c.document_title,
                "version_number": c.version_number,
                "page_number": c.page_number,
                "section": c.section,
                "excerpt": c.text[:400],
                "score": round(max(c.dense_score, c.keyword_rank, c.fused_score), 4),
            }
        )
    return citations
