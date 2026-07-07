"""Background ingestion pipeline:

download -> extract (with OCR fallback) -> clean -> chunk -> embed (batched)
-> upsert Qdrant (dense) + Postgres chunks (keyword/tsvector) -> mark indexed.

The Qdrant point id equals the Postgres chunk id, so the two halves of hybrid
search always refer to the same physical chunk.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, text as sql_text

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal
from app.models.enums import VersionStatus
from app.models.models import Chunk, Document, DocumentVersion
from app.services.embeddings import embed_texts
from app.services.ingestion.chunker import chunk_pages, clean_text
from app.services.ingestion.extract import extract
from app.services.retrieval import vector_store
from app.services.storage import get_storage
from app.workers.celery_app import celery

configure_logging()
logger = get_logger(__name__)

EMBED_BATCH_SIZE = 64


@celery.task(name="ingest_version", bind=True, max_retries=2, default_retry_delay=30)
def ingest_version_task(self, version_id: str) -> None:
    db = SessionLocal()
    try:
        version = db.get(DocumentVersion, uuid.UUID(version_id))
        if not version:
            logger.warning(f"version {version_id} not found; skipping")
            return
        document = db.get(Document, version.document_id)
        version.status = VersionStatus.processing
        db.commit()

        data = get_storage().get(version.storage_key)
        extraction = extract(data, version.mime_type)
        pages = [(p.page_number, clean_text(p.text)) for p in extraction.pages if p.text.strip()]
        if not pages:
            raise ValueError("No extractable text found in document (OCR also empty)")

        settings = get_settings()
        pieces = chunk_pages(
            pages,
            target_tokens=settings.chunk_target_tokens,
            overlap_ratio=settings.chunk_overlap_ratio,
        )
        if not pieces:
            raise ValueError("Chunker produced no chunks")

        # Replace any previous index for this version (idempotent re-runs)
        vector_store.ensure_collection()
        vector_store.delete_by_version(str(version.id))
        db.execute(delete(Chunk).where(Chunk.version_id == version.id))
        db.commit()

        uploaded_ts = version.created_at.timestamp() if version.created_at else 0.0
        chunk_ids = [uuid.uuid4() for _ in pieces]

        for start in range(0, len(pieces), EMBED_BATCH_SIZE):
            batch = pieces[start : start + EMBED_BATCH_SIZE]
            batch_ids = chunk_ids[start : start + EMBED_BATCH_SIZE]
            vectors = embed_texts([p.text for p in batch])
            points = []
            for cid, piece, vector in zip(batch_ids, batch, vectors):
                db.add(
                    Chunk(
                        id=cid,
                        document_id=document.id,
                        version_id=version.id,
                        chunk_index=piece.chunk_index,
                        text=piece.text,
                        page_number=piece.page_number,
                        section=piece.section,
                    )
                )
                points.append(
                    {
                        "id": str(cid),
                        "vector": vector,
                        "payload": {
                            "document_id": str(document.id),
                            "version_id": str(version.id),
                            "document_title": document.title,
                            "version_number": version.version_number,
                            "category": document.category.value,
                            "tags": document.tags or [],
                            "page_number": piece.page_number,
                            "section": piece.section,
                            "text": piece.text,
                            "uploaded_at_ts": uploaded_ts,
                        },
                    }
                )
            vector_store.upsert_chunks(points)
            db.commit()

        # tsvector for keyword search
        db.execute(
            sql_text(
                "UPDATE chunks SET tsv = to_tsvector('english', text) "
                "WHERE version_id = :vid AND tsv IS NULL"
            ),
            {"vid": str(version.id)},
        )

        # supersede older indexed versions so retrieval only sees the latest
        for old in document.versions:
            if old.id != version.id and old.status == VersionStatus.indexed:
                old.status = VersionStatus.superseded
                vector_store.delete_by_version(str(old.id))
                db.execute(delete(Chunk).where(Chunk.version_id == old.id))

        version.status = VersionStatus.indexed
        version.page_count = extraction.page_count
        version.chunk_count = len(pieces)
        version.ocr_pages = extraction.ocr_pages
        version.indexed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(
            "ingestion complete",
            extra={"extra_fields": {"version_id": version_id, "chunks": len(pieces), "ocr_pages": extraction.ocr_pages}},
        )
    except Exception as exc:
        db.rollback()
        version = db.get(DocumentVersion, uuid.UUID(version_id))
        if version:
            version.status = VersionStatus.failed
            version.error = str(exc)[:2000]
            db.commit()
        logger.exception(f"ingestion failed for version {version_id}")
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery.task(name="purge_document")
def purge_document_task(document_id: str) -> None:
    """Remove vectors, chunks, and stored files for a soft-deleted document."""
    db = SessionLocal()
    try:
        document = db.get(Document, uuid.UUID(document_id))
        if not document:
            return
        for version in document.versions:
            vector_store.delete_by_version(str(version.id))
            db.execute(delete(Chunk).where(Chunk.version_id == version.id))
            if version.storage_key:
                get_storage().delete(version.storage_key)
        db.commit()
    finally:
        db.close()
