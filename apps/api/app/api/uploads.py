# IP — Caramurú Construções — assinatura do autor

"""TUS-like resumable audit-photo uploads backed by MinIO."""

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import anyio
from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.auth import DB, Principal
from app.core.config import settings
from app.models.safety import AuditPhoto, UploadSession

router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])
ALLOWED_TYPES = {"image/webp"}


class UploadCreate(BaseModel):
    photo_id: UUID
    project_id: UUID
    apr_id: UUID | None = None
    work_permit_id: UUID | None = None
    size_bytes: int = Field(gt=0, le=settings.upload_max_bytes)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    content_type: str = "image/webp"
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(ge=0, le=5_000)
    gnss_timestamp: datetime
    captured_at: datetime
    watermark_text: str = Field(min_length=20, max_length=2_000)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)


async def _session(db, principal, upload_id: UUID) -> UploadSession:
    session = await db.scalar(
        select(UploadSession).where(
            UploadSession.id == upload_id, UploadSession.company_id == principal.tenant_id
        )
    )
    if not session:
        raise HTTPException(404, "Upload não encontrada")
    return session


def _temp_path(upload_id: UUID) -> str:
    root = Path(settings.upload_temp_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return str((root / f"{upload_id}.part").resolve())


def _append_chunk(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(body)


def _digest_file(path: Path, expected_size: int) -> str | None:
    if not path.exists() or path.stat().st_size != expected_size:
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _remove_file(path: Path) -> None:
    path.unlink(missing_ok=True)


@router.post("", status_code=201)
async def create_upload(body: UploadCreate, db: DB, principal: Principal):
    if body.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Somente WebP é aceito")
    now = datetime.now(UTC)
    if body.gnss_timestamp.astimezone(UTC) > now + timedelta(minutes=5):
        raise HTTPException(422, "Timestamp GNSS futuro")
    object_key = f"audit/{principal.tenant_id}/{body.project_id}/{body.photo_id}.webp"
    existing = await db.scalar(
        select(AuditPhoto).where(
            AuditPhoto.company_id == principal.tenant_id, AuditPhoto.id == body.photo_id
        )
    )
    if existing:
        session = await db.scalar(
            select(UploadSession).where(UploadSession.photo_id == existing.id)
        )
        if session:
            return {
                "upload_id": session.id,
                "photo_id": existing.id,
                "offset": session.offset_bytes,
                "length": session.total_bytes,
                "chunk_size": session.chunk_size,
            }
        raise HTTPException(409, "Foto já cadastrada sem sessão de upload")
    photo = AuditPhoto(
        id=body.photo_id,
        company_id=principal.tenant_id,
        project_id=body.project_id,
        apr_id=body.apr_id,
        work_permit_id=body.work_permit_id,
        captured_by=principal.user_id,
        object_key=object_key,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        sha256=body.sha256.lower(),
        status="PENDING_UPLOAD",
        latitude=body.latitude,
        longitude=body.longitude,
        accuracy_m=body.accuracy_m,
        gnss_timestamp=body.gnss_timestamp.astimezone(UTC),
        watermark_text=body.watermark_text,
        captured_at=body.captured_at.astimezone(UTC),
        width=body.width,
        height=body.height,
    )
    upload_id = uuid4()
    session = UploadSession(
        id=upload_id,
        company_id=principal.tenant_id,
        photo_id=body.photo_id,
        object_key=object_key,
        total_bytes=body.size_bytes,
        offset_bytes=0,
        chunk_size=settings.upload_chunk_size,
        sha256=body.sha256.lower(),
        status="CREATED",
        content_type=body.content_type,
        temp_path=_temp_path(upload_id),
        created_by=principal.user_id,
    )
    db.add_all([photo, session])
    await db.flush()
    return {
        "upload_id": upload_id,
        "photo_id": body.photo_id,
        "offset": 0,
        "length": body.size_bytes,
        "chunk_size": session.chunk_size,
    }


@router.get("/{upload_id}")
async def upload_status(upload_id: UUID, db: DB, principal: Principal):
    session = await _session(db, principal, upload_id)
    return {
        "upload_id": session.id,
        "photo_id": session.photo_id,
        "offset": session.offset_bytes,
        "length": session.total_bytes,
        "status": session.status,
        "chunk_size": session.chunk_size,
    }


@router.patch("/{upload_id}", status_code=204)
async def upload_chunk(
    upload_id: UUID,
    request: Request,
    response: Response,
    db: DB,
    principal: Principal,
    upload_offset: int = Header(ge=0, alias="Upload-Offset"),
):
    session = await _session(db, principal, upload_id)
    if session.status in {"COMPLETED", "ABORTED"}:
        raise HTTPException(409, "Sessão não aceita mais dados")
    if upload_offset != session.offset_bytes:
        raise HTTPException(409, {"message": "Offset divergente", "offset": session.offset_bytes})
    body = await request.body()
    if (
        not body
        or len(body) > session.chunk_size
        or session.offset_bytes + len(body) > session.total_bytes
    ):
        raise HTTPException(413, "Chunk inválido")
    path = Path(session.temp_path)
    await anyio.to_thread.run_sync(_append_chunk, path, body)
    session.offset_bytes += len(body)
    session.status = "UPLOADING"
    photo = await db.scalar(
        select(AuditPhoto).where(
            AuditPhoto.id == session.photo_id, AuditPhoto.company_id == principal.tenant_id
        )
    )
    if photo:
        photo.status = "UPLOADING"
    response.headers["Upload-Offset"] = str(session.offset_bytes)
    response.headers["Upload-Length"] = str(session.total_bytes)
    response.headers["Tus-Resumable"] = "1.0.0"
    await db.flush()


@router.post("/{upload_id}/complete")
async def complete_upload(upload_id: UUID, db: DB, principal: Principal):
    session = await _session(db, principal, upload_id)
    if session.offset_bytes != session.total_bytes:
        raise HTTPException(409, "Upload incompleto")
    path = Path(session.temp_path)
    digest = await anyio.to_thread.run_sync(_digest_file, path, session.total_bytes)
    if digest is None:
        raise HTTPException(409, "Arquivo temporário ausente ou truncado")
    if digest != session.sha256:
        raise HTTPException(422, "Hash SHA-256 da foto não confere")
    try:
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=settings.minio_use_ssl,
        )
        client.fput_object(
            settings.minio_bucket, session.object_key, str(path), content_type=session.content_type
        )
    except ImportError as exc:
        raise HTTPException(503, "Cliente MinIO não instalado") from exc
    except Exception as exc:
        raise HTTPException(503, "Falha ao persistir objeto no MinIO") from exc
    session.status = "COMPLETED"
    photo = await db.scalar(
        select(AuditPhoto).where(
            AuditPhoto.id == session.photo_id, AuditPhoto.company_id == principal.tenant_id
        )
    )
    if photo:
        photo.status = "UPLOADED"
    await db.flush()
    await anyio.to_thread.run_sync(_remove_file, path)
    return {"photo_id": session.photo_id, "object_key": session.object_key, "status": "UPLOADED"}


@router.delete("/{upload_id}", status_code=204)
async def abort_upload(upload_id: UUID, db: DB, principal: Principal):
    session = await _session(db, principal, upload_id)
    session.status = "ABORTED"
    path = Path(session.temp_path)
    await anyio.to_thread.run_sync(_remove_file, path)
    photo = await db.scalar(
        select(AuditPhoto).where(
            AuditPhoto.id == session.photo_id, AuditPhoto.company_id == principal.tenant_id
        )
    )
    if photo:
        photo.status = "REJECTED"
    await db.flush()
