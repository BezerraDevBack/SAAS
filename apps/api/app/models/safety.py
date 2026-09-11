# IP — Caramurú Construções — assinatura do autor

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class WorkPermit(UUIDPrimaryKeyMixin, Base):
    """Permissão de trabalho liberada somente após APR, EPI/EPC e assinaturas."""

    __tablename__ = "work_permits"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_SIGNATURE', 'RELEASED', 'EXPIRED', 'BLOCKED')",
            name="work_permit_status",
        ),
        CheckConstraint(
            "work_height_m IS NULL OR work_height_m >= 0", name="work_height_non_negative"
        ),
        CheckConstraint("voltage_kv IS NULL OR voltage_kv >= 0", name="work_voltage_non_negative"),
        Index("ix_work_permits_tenant_status", "company_id", "status"),
    )

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    apr_id: Mapped[UUID] = mapped_column(ForeignKey("aprs.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    activity: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    requires_nr10: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_nr35: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    voltage_kv: Mapped[float | None] = mapped_column(nullable=True)
    work_height_m: Mapped[float | None] = mapped_column(nullable=True)
    epi_checklist: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    epc_checklist: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    hazards: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    tst_signature: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    encarregado_signature: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditPhoto(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_photos"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING_UPLOAD', 'UPLOADING', 'UPLOADED', 'REJECTED')",
            name="audit_photo_status",
        ),
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="audit_photo_latitude"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="audit_photo_longitude"),
        CheckConstraint("accuracy_m >= 0", name="audit_photo_accuracy"),
        Index("ix_audit_photos_tenant_project", "company_id", "project_id"),
    )

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    apr_id: Mapped[UUID | None] = mapped_column(ForeignKey("aprs.id"), nullable=True, index=True)
    work_permit_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("work_permits.id"), nullable=True, index=True
    )
    captured_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="image/webp")
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_UPLOAD")
    latitude: Mapped[float] = mapped_column(nullable=False)
    longitude: Mapped[float] = mapped_column(nullable=False)
    accuracy_m: Mapped[float] = mapped_column(nullable=False)
    gnss_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    watermark_text: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UploadSession(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "upload_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CREATED', 'UPLOADING', 'COMPLETED', 'ABORTED')",
            name="upload_session_status",
        ),
        CheckConstraint(
            "offset_bytes >= 0 AND total_bytes > 0 AND offset_bytes <= total_bytes",
            name="upload_offsets",
        ),
    )

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    photo_id: Mapped[UUID] = mapped_column(
        ForeignKey("audit_photos.id"), nullable=False, unique=True
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    offset_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    chunk_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=8 * 1024 * 1024)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATED")
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="image/webp")
    temp_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
