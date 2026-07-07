"""OpenAI embeddings with a Redis cache for query embeddings.

Documents and queries MUST use the same model — the model name is part of the
cache key so a model change never serves stale vectors."""
import hashlib
import json

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.redis_client import get_redis

_client: OpenAI | None = None
QUERY_CACHE_TTL = 60 * 60 * 24  # 24h


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=get_settings().openai_api_key)
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def embed_texts(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    response = _get_client().embeddings.create(
        model=settings.openai_embedding_model,
        input=texts,
        dimensions=settings.embedding_dimensions,
    )
    return [item.embedding for item in response.data]


def embed_query(query: str) -> list[float]:
    settings = get_settings()
    normalized = " ".join(query.lower().split())
    key = "embcache:" + hashlib.sha256(
        f"{settings.openai_embedding_model}:{settings.embedding_dimensions}:{normalized}".encode()
    ).hexdigest()
    r = get_redis()
    cached = r.get(key)
    if cached:
        return json.loads(cached)
    vector = embed_texts([query])[0]
    r.setex(key, QUERY_CACHE_TTL, json.dumps(vector))
    return vector
