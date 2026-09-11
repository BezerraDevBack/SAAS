# IP — Caramurú Construções — assinatura do autor

"""initial schema: tenants, users, projects (postgis), assets

Revision ID: 001_initial
Revises:
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    user_role = postgresql.ENUM(
        "DIRETOR",
        "ENGENHEIRO_RESIDENTE",
        "TST",
        "ENCARREGADO",
        "FISCAL",
        name="user_role",
    )
    project_type = postgresql.ENUM(
        "SUBESTACAO",
        "LINHA_TRANSMISSAO",
        name="project_type",
    )
    project_status = postgresql.ENUM(
        "PLANEJAMENTO",
        "EXECUCAO",
        "PARALISADA",
        "CONCLUIDA",
        name="project_status",
    )
    asset_type = postgresql.ENUM(
        "CURVADORA",
        "GUINCHO",
        "ANDAIME",
        name="asset_type",
    )
    asset_status = postgresql.ENUM(
        "DISPONIVEL",
        "EM_USO",
        "MANUTENCAO",
        "INATIVO",
        name="asset_status",
    )
    user_role.create(op.get_bind(), checkfirst=True)
    project_type.create(op.get_bind(), checkfirst=True)
    project_status.create(op.get_bind(), checkfirst=True)
    asset_type.create(op.get_bind(), checkfirst=True)
    asset_status.create(op.get_bind(), checkfirst=True)
    # ENUMs were created explicitly above. Table DDL must not create them a second time.
    for enum_type in (user_role, project_type, project_status, asset_type, asset_status):
        enum_type.create_type = False

    op.create_table(
        "companies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("tax_id", sa.String(length=18), nullable=True, comment="CNPJ"),
        sa.Column("legal_name", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_companies"),
        sa.UniqueConstraint("slug", name="uq_companies_slug"),
    )
    op.create_index("ix_companies_slug", "companies", ["slug"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_users_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("company_id", "email", name="uq_users_company_email"),
    )
    op.create_index("ix_users_company_id", "users", ["company_id"], unique=False)

    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("project_type", project_type, nullable=False),
        sa.Column(
            "status",
            project_status,
            nullable=False,
            server_default="PLANEJAMENTO",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("voltage_kv", sa.String(length=32), nullable=True),
        sa.Column(
            "geometry",
            Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
            nullable=True,
            comment="Subestação: Point/Polygon. LT: LineString. SRID 4326.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_projects_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
    )
    op.create_index("ix_projects_company_id", "projects", ["company_id"], unique=False)
    op.create_index("ix_projects_code", "projects", ["code"], unique=False)
    op.execute(
        "CREATE INDEX ix_projects_geometry ON projects USING gist (geometry)"
    )

    op.create_table(
        "assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_type", asset_type, nullable=False),
        sa.Column(
            "status",
            asset_status,
            nullable=False,
            server_default="DISPONIVEL",
        ),
        sa.Column("serial_number", sa.String(length=128), nullable=False),
        sa.Column("qr_code", sa.String(length=128), nullable=False),
        sa.Column("manufacturer", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_assets_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_assets_project_id_projects",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assets"),
        sa.UniqueConstraint("qr_code", name="uq_assets_qr_code"),
        sa.UniqueConstraint("company_id", "serial_number", name="uq_assets_company_serial"),
    )
    op.create_index("ix_assets_company_id", "assets", ["company_id"], unique=False)
    op.create_index("ix_assets_project_id", "assets", ["project_id"], unique=False)
    op.create_index("ix_assets_qr_code", "assets", ["qr_code"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_assets_qr_code", table_name="assets")
    op.drop_index("ix_assets_project_id", table_name="assets")
    op.drop_index("ix_assets_company_id", table_name="assets")
    op.drop_table("assets")

    op.execute("DROP INDEX IF EXISTS ix_projects_geometry")
    op.drop_index("ix_projects_code", table_name="projects")
    op.drop_index("ix_projects_company_id", table_name="projects")
    op.drop_table("projects")

    op.drop_index("ix_users_company_id", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_companies_slug", table_name="companies")
    op.drop_table("companies")

    op.execute("DROP TYPE IF EXISTS asset_status")
    op.execute("DROP TYPE IF EXISTS asset_type")
    op.execute("DROP TYPE IF EXISTS project_status")
    op.execute("DROP TYPE IF EXISTS project_type")
    op.execute("DROP TYPE IF EXISTS user_role")
