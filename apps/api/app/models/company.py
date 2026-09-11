# IP — Caramurú Construções — assinatura do autor

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant raiz (multi-tenant). Toda entidade de negócio referencia `companies.id`."""

    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("slug", name="uq_companies_slug"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    tax_id: Mapped[str | None] = mapped_column(String(18), nullable=True, comment="CNPJ")
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    users: Mapped[list["User"]] = relationship(back_populates="company")  # noqa: F821
    projects: Mapped[list["Project"]] = relationship(back_populates="company")  # noqa: F821
    assets: Mapped[list["Asset"]] = relationship(back_populates="company")  # noqa: F821
