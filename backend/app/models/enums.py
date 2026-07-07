import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    doctor = "doctor"
    researcher = "researcher"


class DocumentCategory(str, enum.Enum):
    clinical_guideline = "clinical_guideline"
    research_paper = "research_paper"
    sop = "sop"
    treatment_protocol = "treatment_protocol"
    other = "other"


class VersionStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    indexed = "indexed"
    failed = "failed"
    superseded = "superseded"
