# IP — Caramurú Construções — assinatura do autor

"""Tenant-isolated mutation journal, receipts, field revisions and capture triggers.

Revision ID: 002_sync
Revises: 001_initial
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "002_sync"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "assets",
        sa.Column(
            "sync_field_versions", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.create_unique_constraint("uq_projects_id_company", "projects", ["id", "company_id"])
    op.create_unique_constraint("uq_users_id_company", "users", ["id", "company_id"])
    op.drop_constraint("fk_assets_project_id_projects", "assets", type_="foreignkey")
    op.create_foreign_key(
        "fk_assets_project_tenant",
        "assets",
        "projects",
        ["project_id", "company_id"],
        ["id", "company_id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "sync_clocks",
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("companies.id"), primary_key=True),
        sa.Column("timestamp", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_table(
        "sync_changes",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("table_name", sa.String(32), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("operation", sa.String(6), nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("client_version", sa.String(100), nullable=False),
        sa.Column("server_timestamp", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("operation IN ('CREATE', 'UPDATE', 'DELETE')", name="operation"),
    )
    op.create_index(
        "ix_sync_changes_tenant_cursor", "sync_changes", ["tenant_id", "server_timestamp"]
    )
    op.create_index(
        "ix_sync_changes_record", "sync_changes", ["tenant_id", "table_name", "record_id"]
    )
    op.create_table(
        "sync_batches",
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("companies.id"), primary_key=True),
        sa.Column("author_id", sa.UUID(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("batch_id", sa.UUID(), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("response", JSONB, nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id", "tenant_id"],
            ["users.id", "users.company_id"],
            name="fk_sync_batches_author_tenant",
        ),
    )
    for table in ("inspections", "aprs"):
        op.create_table(
            table,
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("company_id", sa.UUID(), sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("parent_id", sa.UUID(), nullable=True),
            sa.Column("observation", sa.Text(), nullable=False),
            sa.Column("author_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("author_hash", sa.String(64), nullable=False),
            sa.Column("author_role", sa.String(32), nullable=False),
            sa.Column("client_version", sa.String(100), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("id", "company_id", "project_id", name=f"uq_{table}_parent_scope"),
            sa.ForeignKeyConstraint(
                ["project_id", "company_id"],
                ["projects.id", "projects.company_id"],
                name=f"fk_{table}_project_tenant",
            ),
            sa.ForeignKeyConstraint(
                ["author_id", "company_id"],
                ["users.id", "users.company_id"],
                name=f"fk_{table}_author_tenant",
            ),
            sa.ForeignKeyConstraint(
                ["parent_id", "company_id", "project_id"],
                [f"{table}.id", f"{table}.company_id", f"{table}.project_id"],
            ),
            sa.CheckConstraint(
                "parent_id IS NULL OR parent_id <> id", name=f"{table}_not_own_parent"
            ),
        )

    op.execute("""
        CREATE FUNCTION sync_next_timestamp(t uuid) RETURNS bigint LANGUAGE plpgsql AS $$
        DECLARE result bigint;
        BEGIN
          INSERT INTO sync_clocks(tenant_id, timestamp) VALUES(t, 0) ON CONFLICT DO NOTHING;
          UPDATE sync_clocks SET timestamp = greatest(timestamp + 1,
            floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint)
            WHERE tenant_id = t RETURNING timestamp INTO result;
          IF result IS NULL THEN RAISE EXCEPTION 'Tenant scope unavailable'; END IF;
          RETURN result;
        END $$;
    """)
    op.execute("""
        CREATE FUNCTION sync_capture_change() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
          t uuid; rid uuid; stamp bigint; payload jsonb; previous jsonb;
          version text; field text; rank integer;
        BEGIN
          IF TG_TABLE_NAME IN ('inspections', 'aprs') AND TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION 'Field revisions are append-only' USING ERRCODE = '23514';
          END IF;
          IF TG_OP = 'UPDATE' AND (NEW.id <> OLD.id OR NEW.company_id <> OLD.company_id) THEN
            RAISE EXCEPTION 'Record identity and tenant are immutable' USING ERRCODE = '23514';
          END IF;
          IF TG_OP = 'DELETE' THEN
            t := OLD.company_id; rid := OLD.id; payload := jsonb_build_object('id', rid);
          ELSE
            t := NEW.company_id; rid := NEW.id;
            payload := to_jsonb(NEW) - 'company_id' - 'sync_field_versions';
            IF TG_TABLE_NAME = 'projects' THEN
              payload := jsonb_set(payload, '{geometry}', coalesce(to_jsonb(ST_AsGeoJSON(NEW.geometry)), 'null'));
            END IF;
            payload := jsonb_set(payload, '{created_at}',
              to_jsonb(floor(extract(epoch FROM NEW.created_at) * 1000)::bigint));
            IF TG_TABLE_NAME IN ('projects', 'assets') THEN
              payload := jsonb_set(payload, '{updated_at}',
                to_jsonb(floor(extract(epoch FROM NEW.updated_at) * 1000)::bigint));
            END IF;
          END IF;
          stamp := sync_next_timestamp(t);
          version := coalesce(nullif(current_setting('app.client_version', true), ''),
            lpad(stamp::text, 13, '0') || ':000000:server');
          IF TG_TABLE_NAME = 'assets' AND TG_OP <> 'DELETE' THEN
            -- All writers, including future CRUD/SQL writes, participate in conflict tracking.
            rank := coalesce(nullif(current_setting('app.author_rank', true), '')::integer, 100);
            IF TG_OP = 'UPDATE' THEN previous := to_jsonb(OLD); ELSE previous := '{}'::jsonb; END IF;
            IF TG_OP = 'UPDATE' THEN
              NEW.sync_field_versions := OLD.sync_field_versions;
            ELSE NEW.sync_field_versions := '{}'::jsonb; END IF;
            FOR field IN SELECT jsonb_object_keys(payload - 'id' - 'created_at' - 'updated_at') LOOP
              IF TG_OP = 'INSERT' OR (payload->field) IS DISTINCT FROM (previous->field)
                OR coalesce(nullif(current_setting('app.changed_fields', true), ''), '[]')::jsonb ? field THEN
                NEW.sync_field_versions := jsonb_set(NEW.sync_field_versions, ARRAY[field],
                  jsonb_build_object('rank', rank, 'hlc', version, 'timestamp', stamp));
              END IF;
            END LOOP;
          END IF;
          INSERT INTO sync_changes(id, tenant_id, table_name, record_id, operation, data,
                                   client_version, server_timestamp)
          VALUES(gen_random_uuid(), t, TG_TABLE_NAME, rid,
            CASE TG_OP WHEN 'INSERT' THEN 'CREATE' WHEN 'UPDATE' THEN 'UPDATE' ELSE 'DELETE' END,
            payload, version, stamp);
          IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
        END $$;
    """)
    for table in ("projects", "assets", "inspections", "aprs"):
        op.execute(
            f"CREATE TRIGGER capture_sync BEFORE INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION sync_capture_change()"
        )

    # Seed existing records into the journal as CREATE events, including geometries and dates.
    for table in ("projects", "assets"):
        geometry = (
            " || jsonb_build_object('geometry', ST_AsGeoJSON(r.geometry))"
            if table == "projects"
            else ""
        )
        op.execute(f"""
            INSERT INTO sync_changes
              (id, tenant_id, table_name, record_id, operation, data, client_version, server_timestamp)
            SELECT gen_random_uuid(), r.company_id, '{table}', r.id, 'CREATE',
              (to_jsonb(r) - 'company_id' - 'sync_field_versions') || jsonb_build_object(
                'created_at', floor(extract(epoch FROM r.created_at)*1000)::bigint,
                'updated_at', floor(extract(epoch FROM r.updated_at)*1000)::bigint){geometry},
              '0000000000000:000000:bootstrap', sync_next_timestamp(r.company_id)
            FROM {table} r
        """)
    op.execute("""
        CREATE FUNCTION sync_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Sync journal and receipts are immutable' USING ERRCODE = '23514'; END $$;
    """)
    for table in ("sync_changes", "sync_batches"):
        op.execute(
            f"CREATE TRIGGER immutable_sync BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION sync_immutable()"
        )
    for table in (
        "companies",
        "users",
        "projects",
        "assets",
        "inspections",
        "aprs",
        "sync_clocks",
        "sync_changes",
        "sync_batches",
    ):
        column = (
            "id"
            if table == "companies"
            else ("tenant_id" if table.startswith("sync_") else "company_id")
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        predicate = f"{column} = nullif(current_setting('app.tenant_id', true), '')::uuid"
        op.execute(
            f"CREATE POLICY tenant_scope ON {table} USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade():
    for table in (
        "companies",
        "users",
        "projects",
        "assets",
        "inspections",
        "aprs",
        "sync_clocks",
        "sync_changes",
        "sync_batches",
    ):
        op.execute(f"DROP POLICY tenant_scope ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    for table in ("projects", "assets", "inspections", "aprs"):
        op.execute(f"DROP TRIGGER capture_sync ON {table}")
    op.execute("DROP FUNCTION sync_capture_change()")
    for table in ("inspections", "aprs", "sync_batches", "sync_changes"):
        op.drop_table(table)
    op.execute("DROP FUNCTION sync_immutable()")
    op.execute("DROP FUNCTION sync_next_timestamp(uuid)")
    op.drop_table("sync_clocks")
    op.drop_constraint("fk_assets_project_tenant", "assets", type_="foreignkey")
    op.create_foreign_key(
        "fk_assets_project_id_projects",
        "assets",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("uq_projects_id_company", "projects", type_="unique")
    op.drop_constraint("uq_users_id_company", "users", type_="unique")
    op.drop_column("assets", "sync_field_versions")
