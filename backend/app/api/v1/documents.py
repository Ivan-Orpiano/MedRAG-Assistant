import hashlib
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_admin, require_uploader
from app.core.rate_limit import enforce_rate_limit
from app.models.enums import DocumentCategory, VersionStatus
from app.models.models import Document, DocumentVersion, UsageEvent, User
from app.schemas.schemas import DocumentOut, DocumentUpdate
from app.db.session import get_db
from app.services.ingestion.extract import SUPPORTED_MIME
from app.services.storage import get_storage
from app.workers.tasks import ingest_version_task

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


def _validate_upload(file: UploadFile, data: bytes) -> str:
    mime = file.content_type or ""
    if mime not in SUPPORTED_MIME:
        # fall back to extension sniffing for permissive clients
        name = (file.filename or "").lower()
        mime = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain",
        }.get(name[name.rfind("."):], "")
    if mime not in SUPPORTED_MIME:
        raise HTTPException(415, "Only PDF, DOCX, and TXT files are supported")
    if len(data) == 0:
        raise HTTPException(400, "Uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_UPLOAD_BYTES // (1024*1024)} MB limit")
    return mime


def _store_and_queue(
    db: Session, document: Document, file: UploadFile, data: bytes, mime: str, version_number: int
) -> DocumentVersion:
    checksum = hashlib.sha256(data).hexdigest()
    version = DocumentVersion(
        document_id=document.id,
        version_number=version_number,
        original_filename=file.filename or "upload",
        storage_key="",
        mime_type=mime,
        file_size=len(data),
        checksum_sha256=checksum,
        status=VersionStatus.pending,
    )
    db.add(version)
    db.flush()
    version.storage_key = f"documents/{document.id}/v{version_number}/{version.id}"
    get_storage().put(version.storage_key, data)
    db.commit()
    ingest_version_task.delay(str(version.id))
    return version


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(..., max_length=500),
    category: DocumentCategory = Form(...),
    description: str | None = Form(None),
    tags: str | None = Form(None, description="Comma-separated tags"),
    db: Session = Depends(get_db),
    user: User = Depends(require_uploader),
):
    enforce_rate_limit(request, "upload", str(user.id))
    data = await file.read()
    mime = _validate_upload(file, data)

    document = Document(
        title=title,
        description=description,
        category=category,
        tags=[t.strip() for t in tags.split(",") if t.strip()] if tags else [],
        created_by=user.id,
    )
    db.add(document)
    db.flush()
    _store_and_queue(db, document, file, data, mime, version_number=1)
    db.add(UsageEvent(user_id=user.id, event_type="upload", meta={"document_id": str(document.id)}))
    db.commit()
    db.refresh(document)
    return _load_document(db, document.id)


@router.post("/{document_id}/versions", response_model=DocumentOut, status_code=201)
async def upload_new_version(
    request: Request,
    document_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_uploader),
):
    enforce_rate_limit(request, "upload", str(user.id))
    document = _get_document_or_404(db, document_id)
    data = await file.read()
    mime = _validate_upload(file, data)
    latest = max((v.version_number for v in document.versions), default=0)
    _store_and_queue(db, document, file, data, mime, version_number=latest + 1)
    db.commit()
    return _load_document(db, document.id)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    category: DocumentCategory | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = (
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.is_deleted == False)  # noqa: E712
        .order_by(Document.updated_at.desc())
    )
    if category:
        stmt = stmt.where(Document.category == category)
    return db.scalars(stmt).all()


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _get_document_or_404(db, document_id)


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: uuid.UUID,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_uploader),
):
    document = _get_document_or_404(db, document_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(document, field, value)
    db.commit()
    return _load_document(db, document.id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    from app.workers.tasks import purge_document_task

    document = _get_document_or_404(db, document_id)
    document.is_deleted = True  # soft delete; purge task removes vectors + files
    db.add(UsageEvent(user_id=user.id, event_type="delete", meta={"document_id": str(document_id)}))
    db.commit()
    purge_document_task.delay(str(document_id))


@router.post("/{document_id}/versions/{version_id}/reindex", status_code=202)
def reindex_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    version = db.get(DocumentVersion, version_id)
    if not version or version.document_id != document_id:
        raise HTTPException(404, "Version not found")
    version.status = VersionStatus.pending
    version.error = None
    db.commit()
    ingest_version_task.delay(str(version_id))
    return {"status": "queued"}


def _get_document_or_404(db: Session, document_id: uuid.UUID) -> Document:
    document = _load_document(db, document_id)
    if not document or document.is_deleted:
        raise HTTPException(404, "Document not found")
    return document


def _load_document(db: Session, document_id: uuid.UUID) -> Document | None:
    return db.scalar(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.id == document_id)
    )
