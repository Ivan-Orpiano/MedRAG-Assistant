from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.enums import VersionStatus
from app.models.models import Chunk, Document, DocumentVersion, Message, UsageEvent, User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
def system_stats(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    version_counts = dict(
        db.execute(
            select(DocumentVersion.status, func.count()).group_by(DocumentVersion.status)
        ).all()
    )
    events_7d = dict(
        db.execute(
            select(UsageEvent.event_type, func.count())
            .where(UsageEvent.created_at >= week_ago)
            .group_by(UsageEvent.event_type)
        ).all()
    )
    grounded = db.scalar(
        select(func.count()).select_from(Message).where(Message.role == "assistant", Message.grounded == True)  # noqa: E712
    )
    refused = db.scalar(
        select(func.count()).select_from(Message).where(Message.role == "assistant", Message.grounded == False)  # noqa: E712
    )
    avg_latency = db.scalar(
        select(func.avg(Message.latency_ms)).where(Message.role == "assistant")
    )

    return {
        "documents": db.scalar(select(func.count()).select_from(Document).where(Document.is_deleted == False)),  # noqa: E712
        "chunks": db.scalar(select(func.count()).select_from(Chunk)),
        "users": db.scalar(select(func.count()).select_from(User)),
        "versions_by_status": {k.value if hasattr(k, "value") else str(k): v for k, v in version_counts.items()},
        "events_last_7_days": events_7d,
        "answers_grounded": grounded or 0,
        "answers_refused_ungrounded": refused or 0,
        "avg_answer_latency_ms": round(avg_latency, 1) if avg_latency else None,
    }


@router.get("/indexing")
def indexing_queue(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.execute(
        select(
            DocumentVersion.id,
            Document.title,
            DocumentVersion.version_number,
            DocumentVersion.status,
            DocumentVersion.error,
            DocumentVersion.chunk_count,
            DocumentVersion.ocr_pages,
            DocumentVersion.created_at,
            DocumentVersion.indexed_at,
        )
        .join(Document, Document.id == DocumentVersion.document_id)
        .order_by(DocumentVersion.created_at.desc())
        .limit(100)
    ).all()
    return [
        {
            "version_id": str(r.id),
            "title": r.title,
            "version": r.version_number,
            "status": r.status.value if isinstance(r.status, VersionStatus) else str(r.status),
            "error": r.error,
            "chunks": r.chunk_count,
            "ocr_pages": r.ocr_pages,
            "created_at": r.created_at.isoformat(),
            "indexed_at": r.indexed_at.isoformat() if r.indexed_at else None,
        }
        for r in rows
    ]
