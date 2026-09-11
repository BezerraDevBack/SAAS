# IP — Caramurú Construções — assinatura do autor

import enum
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProjectType(enum.StrEnum):
    SUBESTACAO = "SUBESTACAO"
    LINHA_TRANSMISSAO = "LINHA_TRANSMISSAO"


class ProjectStatus(enum.StrEnum):
    PLANEJAMENTO = "PLANEJAMENTO"
    EXECUCAO = "EXECUCAO"
    PARALISADA = "PARALISADA"
    CONCLUIDA = "CONCLUIDA"


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Obra: subestação (ponto/polígono) ou linha de transmissão (LineString)."""

    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_projects_id_company"),
        Index("ix_projects_geometry", "geometry", postgresql_using="gist"),
    )

    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_type: Mapped[ProjectType] = mapped_column(
        Enum(ProjectType, name="project_type", native_enum=True),
        nullable=False,
    )
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status", native_enum=True),
        nullable=False,
        default=ProjectStatus.PLANEJAMENTO,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    voltage_kv: Mapped[str | None] = mapped_column(String(32), nullable=True)

    geometry: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
        nullable=True,
        comment="Subestação: Point/Polygon. LT: LineString. SRID 4326.",
    )

    company: Mapped["Company"] = relationship(back_populates="projects")  # noqa: F821
    assets: Mapped[list["Asset"]] = relationship(  # noqa: F821
        back_populates="project", foreign_keys="Asset.project_id", passive_deletes="all"
    )
