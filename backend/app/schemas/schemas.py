import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import DocumentCategory, UserRole, VersionStatus

DISCLAIMER = (
    "This assistant is for educational and research purposes only. It does not "
    "replace professional medical judgment and must not be used to diagnose or "
    "treat patients. Answers are generated strictly from the uploaded document "
    "corpus and include citations for verification."
)


# ---- Auth / users ----
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    full_name: str


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=10, max_length=128)
    role: UserRole


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- Documents ----
class DocumentVersionOut(BaseModel):
    id: uuid.UUID
    version_number: int
    original_filename: str
    mime_type: str
    file_size: int
    status: VersionStatus
    error: str | None
    page_count: int | None
    chunk_count: int | None
    ocr_pages: int
    created_at: datetime
    indexed_at: datetime | None

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    category: DocumentCategory
    tags: list[str] | None
    created_at: datetime
    updated_at: datetime
    versions: list[DocumentVersionOut] = []

    model_config = {"from_attributes": True}


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    description: str | None = None
    category: DocumentCategory | None = None
    tags: list[str] | None = None


# ---- Chat ----
class RetrievalFilters(BaseModel):
    categories: list[DocumentCategory] | None = None
    document_ids: list[uuid.UUID] | None = None
    tags: list[str] | None = None
    uploaded_after: datetime | None = None
    uploaded_before: datetime | None = None


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    question: str = Field(min_length=1, max_length=4000)
    filters: RetrievalFilters | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


class Citation(BaseModel):
    marker: int
    document_id: uuid.UUID
    document_title: str
    version_number: int
    page_number: int | None
    section: str | None
    excerpt: str
    score: float


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list | None
    grounded: bool | None
    created_at: datetime

    model_config = {"from_attributes": True}
