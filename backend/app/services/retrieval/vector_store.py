"""Qdrant wrapper. One point per chunk, id shared with the Postgres chunks row.
Payload carries the metadata needed for filtering and citation without a DB
round-trip."""
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Datatype,
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PointStruct,
    Range,
    VectorParams,
)

from app.core.config import get_settings


@lru_cache
def get_qdrant() -> QdrantClient:
    return QdrantClient(url=get_settings().qdrant_url)


def ensure_collection() -> None:
    settings = get_settings()
    client = get_qdrant()
    if not client.collection_exists(settings.qdrant_collection):
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.embedding_dimensions,
                distance=Distance.COSINE,
                datatype=Datatype.FLOAT16,
            ),
        )


def upsert_chunks(points: list[dict]) -> None:
    """points: [{id, vector, payload}]"""
    settings = get_settings()
    get_qdrant().upsert(
        collection_name=settings.qdrant_collection,
        points=[PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"]) for p in points],
    )


def delete_by_version(version_id: str) -> None:
    settings = get_settings()
    get_qdrant().delete(
        collection_name=settings.qdrant_collection,
        points_selector=Filter(
            must=[FieldCondition(key="version_id", match=MatchAny(any=[version_id]))]
        ),
    )


def build_filter(
    document_ids: list[str] | None = None,
    categories: list[str] | None = None,
    tags: list[str] | None = None,
    uploaded_after_ts: float | None = None,
    uploaded_before_ts: float | None = None,
) -> Filter | None:
    must = []
    if document_ids:
        must.append(FieldCondition(key="document_id", match=MatchAny(any=document_ids)))
    if categories:
        must.append(FieldCondition(key="category", match=MatchAny(any=categories)))
    if tags:
        must.append(FieldCondition(key="tags", match=MatchAny(any=tags)))
    if uploaded_after_ts or uploaded_before_ts:
        must.append(
            FieldCondition(
                key="uploaded_at_ts",
                range=Range(gte=uploaded_after_ts, lte=uploaded_before_ts),
            )
        )
    return Filter(must=must) if must else None


def dense_search(vector: list[float], limit: int, qfilter: Filter | None):
    settings = get_settings()
    return get_qdrant().search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        limit=limit,
        query_filter=qfilter,
        with_payload=True,
    )
