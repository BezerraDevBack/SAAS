# IP — Caramurú Construções — assinatura do autor

import enum
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, ForeignKeyConstraint, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AssetType(enum.StrEnum):
    CURVADORA = "CURVADORA"
    GUINCHO = "GUINCHO"
    ANDAIME = "ANDAIME"


class AssetStatus(enum.StrEnum):
    DISPONIVEL = "DISPONIVEL"
    EM_USO = "EM_USO"
    MANUTENCAO = "MANUTENCAO"
    INATIVO = "INATIVO"


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Equipamento de campo identificável por QR Code."""

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("qr_code", name="uq_assets_qr_code"),
        UniqueConstraint("company_id", "serial_number", name="uq_assets_company_serial"),
        ForeignKeyConstraint(
            ["project_id", "company_id"],
            ["projects.id", "projects.company_id"],
            name="fk_assets_project_tenant",
            ondelete="RESTRICT",
        ),
    )

    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[AssetType] = mapped_column(
        Enum(AssetType, name="asset_type", native_enum=True),
        nullable=False,
    )
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, name="asset_status", native_enum=True),
        nullable=False,
        default=AssetStatus.DISPONIVEL,
    )
    serial_number: Mapped[str] = mapped_column(String(128), nullable=False)
    qr_code: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_field_versions: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    company: Mapped["Company"] = relationship(back_populates="assets")  # noqa: F821
    project: Mapped["Project | None"] = relationship(  # noqa: F821
        back_populates="assets", foreign_keys=[project_id]
    )
