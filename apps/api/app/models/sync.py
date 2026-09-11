# IP — Caramurú Construções — assinatura do autor

"""Persistent mutation receipts, ordered tenant cursors and immutable field evidence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class SyncClock(Base):
    __tablename__ = "sync_clocks"
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), primary_key=True)
    timestamp: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )


class SyncChange(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sync_changes"
    __table_args__ = (
        CheckConstraint("operation IN ('CREATE', 'UPDATE', 'DELETE')", name="operation"),
        Index("ix_sync_changes_tenant_cursor", "tenant_id", "server_timestamp"),
        Index("ix_sync_changes_record", "tenant_id", "table_name", "record_id"),
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    table_name: Mapped[str] = mapped_column(String(32), nullable=False)
    record_id: Mapped[UUID] = mapped_column(nullable=False)
    operation: Mapped[str] = mapped_column(String(6), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    client_version: Mapped[str] = mapped_column(String(100), nullable=False)
    # Integer milliseconds, monotonically increasing per tenant, not a wall-clock filter.
    server_timestamp: Mapped[int] = mapped_column(BigInteger, nullable=False)


class SyncBatch(Base):
    __tablename__ = "sync_batches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["author_id", "tenant_id"],
            ["users.id", "users.company_id"],
            name="fk_sync_batches_author_tenant",
        ),
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), primary_key=True)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    batch_id: Mapped[UUID] = mapped_column(primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)


class RevisionMixin(UUIDPrimaryKeyMixin):
    @declared_attr.directive
    @classmethod
    def __table_args__(cls):
        table = cls.__tablename__
        return (
            UniqueConstraint("id", "company_id", "project_id", name=f"uq_{table}_parent_scope"),
            ForeignKeyConstraint(
                ["project_id", "company_id"],
                ["projects.id", "projects.company_id"],
                name=f"fk_{table}_project_tenant",
            ),
            ForeignKeyConstraint(
                ["author_id", "company_id"],
                ["users.id", "users.company_id"],
                name=f"fk_{table}_author_tenant",
            ),
            ForeignKeyConstraint(
                ["parent_id", "company_id", "project_id"],
                [f"{table}.id", f"{table}.company_id", f"{table}.project_id"],
            ),
            CheckConstraint("parent_id IS NULL OR parent_id <> id", name=f"{table}_not_own_parent"),
        )

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(nullable=True)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    author_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    author_role: Mapped[str] = mapped_column(String(32), nullable=False)
    client_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Inspection(RevisionMixin, Base):
    __tablename__ = "inspections"


class APR(RevisionMixin, Base):
    __tablename__ = "aprs"

    requires_nr10: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_nr35: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    voltage_kv: Mapped[float | None] = mapped_column(nullable=True)
    work_height_m: Mapped[float | None] = mapped_column(nullable=True)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    epi_checklist: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    epc_checklist: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    hazards: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    tst_signature: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    encarregado_signature: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
