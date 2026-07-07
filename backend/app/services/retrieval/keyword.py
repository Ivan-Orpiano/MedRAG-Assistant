"""Keyword search over Postgres tsvector — the sparse half of hybrid retrieval.
Catches exact terms (drug names, dosage codes, acronyms) that dense vectors miss."""
import uuid

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session


def keyword_search(
    db: Session,
    query: str,
    limit: int,
    document_ids: list[uuid.UUID] | None = None,
    categories: list[str] | None = None,
    tags: list[str] | None = None,
) -> list[dict]:
    conditions = ["c.tsv @@ plainto_tsquery('english', :q)", "d.is_deleted = false"]
    params: dict = {"q": query, "limit": limit}
    if document_ids:
        conditions.append("c.document_id = ANY(:doc_ids)")
        params["doc_ids"] = [str(i) for i in document_ids]
    if categories:
        conditions.append("d.category = ANY(:categories)")
        params["categories"] = categories
    if tags:
        conditions.append("d.tags ?| :tags")  # JSONB overlap
        params["tags"] = tags

    sql = f"""
        SELECT c.id, c.document_id, c.version_id, c.text, c.page_number, c.section,
               d.title AS document_title, v.version_number,
               ts_rank(c.tsv, plainto_tsquery('english', :q)) AS rank
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        JOIN document_versions v ON v.id = c.version_id
        WHERE {' AND '.join(conditions)}
        ORDER BY rank DESC
        LIMIT :limit
    """
    rows = db.execute(sql_text(sql), params).mappings().all()
    return [dict(r) for r in rows]
