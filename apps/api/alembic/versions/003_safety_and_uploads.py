# IP — Caramurú Construções — assinatura do autor

"""APR/PT safety rules, audit-photo metadata and resumable upload sessions.

Revision ID: 003_safety
Revises: 002_sync
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "003_safety"
down_revision = "002_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in (
        sa.Column("requires_nr10", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_nr35", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="MEDIUM"),
        sa.Column("voltage_kv", sa.Float(), nullable=True),
        sa.Column("work_height_m", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("epi_checklist", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("epc_checklist", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("hazards", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("tst_signature", JSONB, nullable=True),
        sa.Column("encarregado_signature", JSONB, nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("aprs", column)
    op.create_check_constraint(
        "apr_risk_level", "aprs", "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')"
    )
    op.create_check_constraint(
        "apr_status", "aprs", "status IN ('DRAFT', 'PENDING_SIGNATURE', 'RELEASED', 'EXPIRED', 'BLOCKED')"
    )
    op.create_check_constraint("apr_height_non_negative", "aprs", "work_height_m IS NULL OR work_height_m >= 0")
    op.create_check_constraint("apr_voltage_non_negative", "aprs", "voltage_kv IS NULL OR voltage_kv >= 0")

    op.create_table(
        "work_permits",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("company_id", sa.UUID(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("apr_id", sa.UUID(), sa.ForeignKey("aprs.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("activity", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("requires_nr10", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_nr35", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="MEDIUM"),
        sa.Column("voltage_kv", sa.Float(), nullable=True),
        sa.Column("work_height_m", sa.Float(), nullable=True),
        sa.Column("epi_checklist", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("epc_checklist", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("hazards", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("tst_signature", JSONB, nullable=True),
        sa.Column("encarregado_signature", JSONB, nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('DRAFT', 'PENDING_SIGNATURE', 'RELEASED', 'EXPIRED', 'BLOCKED')", name="work_permit_status"),
        sa.CheckConstraint("work_height_m IS NULL OR work_height_m >= 0", name="work_height_non_negative"),
        sa.CheckConstraint("voltage_kv IS NULL OR voltage_kv >= 0", name="work_voltage_non_negative"),
    )
    op.create_index("ix_work_permits_tenant_status", "work_permits", ["company_id", "status"])
    op.create_index("ix_work_permits_company_id", "work_permits", ["company_id"])
    op.create_index("ix_work_permits_project_id", "work_permits", ["project_id"])
    op.create_index("ix_work_permits_apr_id", "work_permits", ["apr_id"])

    op.create_table(
        "audit_photos",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("company_id", sa.UUID(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("apr_id", sa.UUID(), sa.ForeignKey("aprs.id"), nullable=True),
        sa.Column("work_permit_id", sa.UUID(), sa.ForeignKey("work_permits.id"), nullable=True),
        sa.Column("captured_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False, unique=True),
        sa.Column("content_type", sa.String(64), nullable=False, server_default="image/webp"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING_UPLOAD"),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("accuracy_m", sa.Float(), nullable=False),
        sa.Column("gnss_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("watermark_text", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('PENDING_UPLOAD', 'UPLOADING', 'UPLOADED', 'REJECTED')", name="audit_photo_status"),
        sa.CheckConstraint("latitude >= -90 AND latitude <= 90", name="audit_photo_latitude"),
        sa.CheckConstraint("longitude >= -180 AND longitude <= 180", name="audit_photo_longitude"),
        sa.CheckConstraint("accuracy_m >= 0", name="audit_photo_accuracy"),
    )
    op.create_index("ix_audit_photos_tenant_project", "audit_photos", ["company_id", "project_id"])
    op.create_index("ix_audit_photos_company_id", "audit_photos", ["company_id"])
    op.create_index("ix_audit_photos_project_id", "audit_photos", ["project_id"])
    op.create_index("ix_audit_photos_apr_id", "audit_photos", ["apr_id"])
    op.create_index("ix_audit_photos_work_permit_id", "audit_photos", ["work_permit_id"])

    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("company_id", sa.UUID(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("photo_id", sa.UUID(), sa.ForeignKey("audit_photos.id"), nullable=False, unique=True),
        sa.Column("object_key", sa.String(512), nullable=False, unique=True),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("offset_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("chunk_size", sa.BigInteger(), nullable=False, server_default=str(8 * 1024 * 1024)),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="CREATED"),
        sa.Column("content_type", sa.String(64), nullable=False, server_default="image/webp"),
        sa.Column("temp_path", sa.String(1024), nullable=False),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('CREATED', 'UPLOADING', 'COMPLETED', 'ABORTED')", name="upload_session_status"),
        sa.CheckConstraint("offset_bytes >= 0 AND total_bytes > 0 AND offset_bytes <= total_bytes", name="upload_offsets"),
    )
    op.create_index("ix_upload_sessions_company_id", "upload_sessions", ["company_id"])

    for table in ("work_permits", "audit_photos", "upload_sessions"):
        column = "company_id"
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        predicate = f"{column} = nullif(current_setting('app.tenant_id', true), '')::uuid"
        op.execute(f"CREATE POLICY tenant_scope ON {table} USING ({predicate}) WITH CHECK ({predicate})")


def downgrade() -> None:
    for table in ("work_permits", "audit_photos", "upload_sessions"):
        op.execute(f"DROP POLICY tenant_scope ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS ix_upload_sessions_company_id")
    op.drop_table("upload_sessions")
    op.execute("DROP INDEX IF EXISTS ix_audit_photos_work_permit_id")
    op.execute("DROP INDEX IF EXISTS ix_audit_photos_apr_id")
    op.execute("DROP INDEX IF EXISTS ix_audit_photos_project_id")
    op.execute("DROP INDEX IF EXISTS ix_audit_photos_company_id")
    op.drop_index("ix_audit_photos_tenant_project", table_name="audit_photos")
    op.drop_table("audit_photos")
    op.execute("DROP INDEX IF EXISTS ix_work_permits_apr_id")
    op.execute("DROP INDEX IF EXISTS ix_work_permits_project_id")
    op.execute("DROP INDEX IF EXISTS ix_work_permits_company_id")
    op.drop_index("ix_work_permits_tenant_status", table_name="work_permits")
    op.drop_table("work_permits")
    for name in ("apr_voltage_non_negative", "apr_height_non_negative", "apr_status", "apr_risk_level"):
        op.drop_constraint(name, "aprs", type_="check")
    for column in (
        "released_at", "valid_until", "valid_from", "encarregado_signature", "tst_signature",
        "hazards", "epc_checklist", "epi_checklist", "status", "risk_level", "work_height_m",
        "voltage_kv", "requires_nr35", "requires_nr10",
    ):
        op.drop_column("aprs", column)
