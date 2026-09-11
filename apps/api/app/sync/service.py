# IP — Caramurú Construções — assinatura do autor

import hashlib
import json
import time
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from geojson_pydantic.geometries import Geometry
from pydantic import Field, TypeAdapter, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.auth import ROLE_RANK, TenantPrincipal
from app.core.config import settings
from app.models import APR, Asset, Inspection, Project, SyncBatch, SyncChange, SyncClock
from app.models.asset import AssetStatus, AssetType
from app.models.project import ProjectStatus, ProjectType
from app.models.user import UserRole
from app.sync.schemas import (
    MergeConflict,
    PullResponse,
    PullTableChanges,
    PushRequest,
    PushResponse,
    StrictModel,
    hlc_key,
)

MODELS = {"projects": Project, "assets": Asset, "inspections": Inspection, "aprs": APR}
MANAGERS = {UserRole.DIRETOR, UserRole.ENGENHEIRO_RESIDENTE}


class ProjectData(StrictModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    project_type: ProjectType
    status: ProjectStatus = ProjectStatus.PLANEJAMENTO
    description: str | None = Field(default=None, max_length=20000)
    voltage_kv: str | None = Field(default=None, max_length=32)
    geometry: str | None = Field(default=None, max_length=100000)


class AssetData(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    asset_type: AssetType
    serial_number: str = Field(min_length=1, max_length=128)
    qr_code: str = Field(min_length=1, max_length=128)
    status: AssetStatus = AssetStatus.DISPONIVEL
    project_id: UUID | None = None
    manufacturer: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=20000)


class RevisionData(StrictModel):
    project_id: UUID
    parent_id: UUID | None = None
    observation: str = Field(min_length=1, max_length=20000)
    requires_nr10: bool = False
    requires_nr35: bool = False
    voltage_kv: float | None = Field(default=None, ge=0)
    work_height_m: float | None = Field(default=None, ge=0)
    risk_level: str = Field(default="MEDIUM", pattern=r"^(LOW|MEDIUM|HIGH|CRITICAL)$")
    status: str = Field(
        default="DRAFT", pattern=r"^(DRAFT|PENDING_SIGNATURE|RELEASED|EXPIRED|BLOCKED)$"
    )
    epi_checklist: dict[str, bool] = Field(default_factory=dict)
    epc_checklist: dict[str, bool] = Field(default_factory=dict)
    hazards: list[str] = Field(default_factory=list)
    tst_signature: dict | None = None
    encarregado_signature: dict | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    released_at: datetime | None = None


DATA_MODELS = {
    "projects": ProjectData,
    "assets": AssetData,
    "inspections": RevisionData,
    "aprs": RevisionData,
}


def digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


async def lock_tenant(db: AsyncSession, tenant_id: UUID, cursor: int) -> int:
    await db.execute(
        insert(SyncClock).values(tenant_id=tenant_id, timestamp=0).on_conflict_do_nothing()
    )
    clock = await db.scalar(
        select(SyncClock).where(SyncClock.tenant_id == tenant_id).with_for_update()
    )
    if clock is None:
        raise HTTPException(403, "Tenant unavailable")
    if cursor > clock.timestamp:
        raise HTTPException(409, "Invalid future cursor; reset the local tenant database")
    return clock.timestamp


async def pull(db: AsyncSession, principal: TenantPrincipal, cursor: int) -> PullResponse:
    await lock_tenant(db, principal.tenant_id, cursor)
    timestamp = await db.scalar(
        text("SELECT sync_next_timestamp(:tenant)"), {"tenant": principal.tenant_id}
    )
    # The tenant clock lock is shared with every capture trigger, so no commit can be missed.
    # Fold inside PostgreSQL: send each ID once, with its final state and original creation cursor.
    events = (
        await db.execute(
            text("""
        WITH ranked AS (
          SELECT table_name, record_id, operation, data, server_timestamp,
            min(server_timestamp) OVER (PARTITION BY table_name, record_id) AS first_seen,
            row_number() OVER (PARTITION BY table_name, record_id
                               ORDER BY server_timestamp DESC) AS position
          FROM sync_changes WHERE tenant_id = :tenant AND server_timestamp <= :upper
        )
        SELECT * FROM ranked WHERE position = 1 AND server_timestamp > :cursor
        ORDER BY table_name, record_id
    """),
            {"tenant": principal.tenant_id, "cursor": cursor, "upper": timestamp},
        )
    ).mappings()
    changes = {name: PullTableChanges() for name in MODELS}
    for event in events:
        table = changes[event["table_name"]]
        if event["operation"] == "DELETE":
            # Initial sync contains live records only, as required by WatermelonDB.
            if cursor:
                table.deleted.append(str(event["record_id"]))
        elif event["first_seen"] > cursor:
            table.created.append(_sync_dates(event["data"]))
        else:
            table.updated.append(_sync_dates(event["data"]))
    return PullResponse(changes=changes, timestamp=timestamp)


def _sync_dates(data: dict) -> dict:
    """Expose revision timestamps as WatermelonDB epoch milliseconds."""
    value = dict(data)
    created = value.get("created_at")
    if isinstance(created, datetime):
        value["created_at"] = int(created.timestamp() * 1000)
    elif isinstance(created, str):
        try:
            value["created_at"] = int(
                datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp() * 1000
            )
        except ValueError:
            pass
    return value


async def scoped_record(db, model, record_id, tenant_id):
    return await db.scalar(
        select(model).where(model.id == record_id, model.company_id == tenant_id)
    )


async def latest_event(db, tenant_id, table, record_id):
    return await db.scalar(
        select(SyncChange)
        .where(
            SyncChange.tenant_id == tenant_id,
            SyncChange.table_name == table,
            SyncChange.record_id == record_id,
        )
        .order_by(SyncChange.server_timestamp.desc())
        .limit(1)
    )


def authorize(principal, table, operation):
    if principal.role == UserRole.FISCAL:
        raise HTTPException(403, "FISCAL has read-only sync access")
    if table == "projects" or operation == "DELETE":
        if principal.role not in MANAGERS:
            raise HTTPException(403, "This mutation requires engineering management")
    if table in ("inspections", "aprs") and operation != "CREATE":
        raise HTTPException(409, "Append-only: create a new revision ID with parent_id")


def mutations(request: PushRequest):
    seen = set()
    result = []
    for table, changes in request.changes.items():
        for operation, rows in (
            ("CREATE", changes.created),
            ("UPDATE", changes.updated),
            ("DELETE", [{"id": str(i)} for i in changes.deleted]),
        ):
            for raw in rows:
                try:
                    rid = UUID(str(raw["id"]))
                except (KeyError, ValueError, TypeError) as exc:
                    raise HTTPException(422, "Each mutation requires a UUID id") from exc
                key = (table, rid)
                if key in seen:
                    raise HTTPException(422, "Duplicate record in batch")
                seen.add(key)
                meta = request.metadata.get(table, {}).get(rid)
                if meta is None:
                    raise HTTPException(422, "Missing mutation HLC metadata")
                if (
                    hlc_key(meta.client_version)[0]
                    > int(time.time() * 1000) + settings.sync_max_future_skew_ms
                ):
                    raise HTTPException(422, "HLC exceeds allowed future clock skew")
                result.append((table, operation, rid, raw, meta))
    supplied = {(t, rid) for t, records in request.metadata.items() for rid in records}
    if supplied != seen:
        raise HTTPException(422, "Metadata must match the mutations exactly")
    # Projects before dependents for creation; dependents before projects for deletion.
    result.sort(
        key=lambda m: (
            m[1] == "DELETE",
            -list(MODELS).index(m[0]) if m[1] == "DELETE" else list(MODELS).index(m[0]),
        )
    )
    return result


async def validate_data(db, principal, table, rid, operation, raw, meta, event):
    clean = {
        k: v
        for k, v in raw.items()
        if k not in ("id", "_status", "_changed", "created_at", "updated_at")
    }
    schema = DATA_MODELS[table]
    if set(clean) - schema.model_fields.keys():
        raise HTTPException(422, "Unknown or server-owned record fields")
    if operation == "UPDATE":
        fields = set(meta.changed_fields)
        if not fields or fields - schema.model_fields.keys() or fields - clean.keys():
            raise HTTPException(422, "Updates require an explicit valid changed_fields mask")
        clean = {k: v for k, v in clean.items() if k in fields}
    else:
        fields = set(clean)
    base = {k: v for k, v in (event.data if event else {}).items() if k in schema.model_fields}
    try:
        data = schema.model_validate(base | clean).model_dump()
        if table == "aprs":
            if data["voltage_kv"] is not None and data["voltage_kv"] >= 1:
                data["requires_nr10"] = True
            if data["work_height_m"] is not None and data["work_height_m"] >= 2:
                data["requires_nr35"] = True
            if data["status"] == "RELEASED" and (
                not data["tst_signature"] or not data["encarregado_signature"]
            ):
                raise ValueError("released APR requires both signatures")
        if table == "projects" and data["geometry"] is not None:
            geometry = TypeAdapter(Geometry).validate_json(data["geometry"])
            allowed = (
                {"Point", "Polygon"}
                if data["project_type"] == ProjectType.SUBESTACAO
                else {"LineString"}
            )
            if geometry.type not in allowed:
                raise ValueError("Geometry does not match project type")
    except (ValidationError, ValueError) as exc:
        raise HTTPException(422, "Invalid record data") from exc
    if data.get("project_id"):
        if await scoped_record(db, Project, data["project_id"], principal.tenant_id) is None:
            raise HTTPException(422, "Project reference unavailable in tenant")
    if data.get("parent_id"):
        parent = await scoped_record(db, MODELS[table], data["parent_id"], principal.tenant_id)
        if parent is None or parent.project_id != data["project_id"] or parent.id == rid:
            raise HTTPException(422, "Revision parent unavailable in project")
    return data, fields


async def push(db: AsyncSession, principal: TenantPrincipal, request: PushRequest) -> PushResponse:
    await lock_tenant(db, principal.tenant_id, request.last_pulled_at)
    payload = request.model_dump(mode="json", exclude={"last_pulled_at"})
    payload_hash = digest(payload)
    receipt = await db.get(SyncBatch, (principal.tenant_id, principal.user_id, request.batch_id))
    # Revalidate permissions even when replaying an already committed batch.
    batch = mutations(request)
    for table, operation, *_ in batch:
        authorize(principal, table, operation)
    if receipt:
        if receipt.payload_hash != payload_hash:
            raise HTTPException(409, "batch_id was already used with different data")
        return PushResponse.model_validate(receipt.response)
    conflicts = []
    applied = 0
    for table, operation, rid, raw, meta in batch:
        model = MODELS[table]
        record = await scoped_record(db, model, rid, principal.tenant_id)
        event = await latest_event(db, principal.tenant_id, table, rid)
        await db.execute(
            text("SELECT set_config('app.client_version', :version, true)"),
            {"version": meta.client_version},
        )
        if operation == "DELETE":
            if record is None:
                continue
            if event and event.server_timestamp > request.last_pulled_at:
                raise HTTPException(409, "Record changed before deletion; pull and retry")
            await db.delete(record)
            await db.flush()
            applied += 1
            continue
        if event and event.operation == "DELETE":
            raise HTTPException(409, "Record was deleted; pull before retrying")
        data, fields = await validate_data(db, principal, table, rid, operation, raw, meta, event)
        if record is not None and operation == "CREATE":
            # Stable IDs never overwrite evidence or another concurrent create.
            existing = {k: v for k, v in event.data.items() if k in DATA_MODELS[table].model_fields}
            candidate = DATA_MODELS[table].model_validate(data).model_dump(mode="json")
            if candidate == existing and (
                table not in ("inspections", "aprs")
                or (
                    record.author_id == principal.user_id
                    and record.client_version == meta.client_version
                )
            ):
                continue
            raise HTTPException(409, "Record ID already exists with different contents")
        if record is not None and table == "projects":
            if event and event.server_timestamp > request.last_pulled_at:
                raise HTTPException(409, "Project changed; pull before retrying")
        if record is not None and table == "assets":
            rejected = []
            for field in sorted(fields):
                version = record.sync_field_versions.get(field)
                # Hierarchy resolves concurrent writes. A later, observed edit can change the field.
                if version and version["timestamp"] > request.last_pulled_at:
                    incoming = (ROLE_RANK[principal.role], hlc_key(meta.client_version))
                    current = (version["rank"], hlc_key(version["hlc"]))
                    if incoming == current and data[field] != getattr(record, field):
                        raise HTTPException(409, "HLC reused for different contents")
                    if incoming < current:
                        rejected.append(field)
            fields -= set(rejected)
            if rejected:
                conflicts.append(
                    MergeConflict(table_name=table, record_id=rid, rejected_fields=rejected)
                )
        if record is None:
            if table in ("inspections", "aprs"):
                data.update(
                    author_id=principal.user_id,
                    author_role=principal.role.value,
                    client_version=meta.client_version,
                    created_at=datetime.now(UTC),
                )
                data["author_hash"] = digest(
                    {
                        "tenant_id": str(principal.tenant_id),
                        "id": str(rid),
                        "author_id": str(principal.user_id),
                        "role": principal.role.value,
                        "project_id": str(data["project_id"]),
                        "parent_id": str(data["parent_id"]) if data["parent_id"] else None,
                        "observation": data["observation"],
                        "client_version": meta.client_version,
                    }
                )
            values = data
        else:
            values = {k: v for k, v in data.items() if k in fields}
            if not values:
                continue
        if table == "projects" and values.get("geometry") is not None:
            values["geometry"] = func.ST_SetSRID(func.ST_GeomFromGeoJSON(values["geometry"]), 4326)
        if record is None:
            db.add(model(id=rid, company_id=principal.tenant_id, **values))
        else:
            for key, value in values.items():
                setattr(record, key, value)
            if table == "assets":
                # An explicit edit carries intent even when its value is unchanged.
                # Force SQL so the capture trigger records the winning rank/HLC.
                await db.execute(
                    text("SELECT set_config('app.changed_fields', :fields, true)"),
                    {"fields": json.dumps(sorted(values))},
                )
                for key in values:
                    flag_modified(record, key)
        await db.flush()
        if table == "assets" and record is not None:
            await db.execute(text("SELECT set_config('app.changed_fields', '[]', true)"))
        applied += 1
    response = PushResponse(batch_id=request.batch_id, applied=applied, conflicts=conflicts)
    db.add(
        SyncBatch(
            tenant_id=principal.tenant_id,
            author_id=principal.user_id,
            batch_id=request.batch_id,
            payload_hash=payload_hash,
            response=response.model_dump(mode="json"),
        )
    )
    await db.flush()
    return response
