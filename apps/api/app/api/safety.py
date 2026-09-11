# IP — Caramurú Construções — assinatura do autor

"""Digital APR/PT workflow with mandatory NR-10 and NR-35 controls."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.core.auth import DB, Principal
from app.models.safety import WorkPermit
from app.models.sync import APR
from app.models.user import UserRole

router = APIRouter(prefix="/api/v1/safety", tags=["safety"])

NR10_EPI = (
    "capacete_classe_b",
    "oculos_protecao",
    "luvas_isolantes",
    "luvas_cobertura",
    "vestimenta_anti_arco",
    "calcado_isolante",
    "detector_tensao",
)
NR10_EPC = (
    "barreira_sinalizacao",
    "aterramento_temporario",
    "bloqueio_etiquetagem",
    "delimitacao_area",
)
NR35_EPI = ("cinturao_paraquedista", "talabarte_duplo", "trava_quedas", "capacete_jugular")
NR35_EPC = ("linha_vida", "ponto_ancoragem", "guarda_corpo", "plano_resgate")


class SignatureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signer_role: Literal["TST", "ENCARREGADO"]
    signature_svg: str = Field(min_length=20, max_length=100_000)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    signed_at: datetime


class SafetyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID
    observation: str = Field(min_length=1, max_length=10_000)
    voltage_kv: float | None = Field(default=None, ge=0)
    work_height_m: float | None = Field(default=None, ge=0)
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    epi_checklist: dict[str, bool] = Field(default_factory=dict)
    epc_checklist: dict[str, bool] = Field(default_factory=dict)
    hazards: list[str] = Field(default_factory=list, max_length=100)
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    @model_validator(mode="after")
    def valid_window(self):
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("valid_until deve ser posterior a valid_from")
        return self


class PermitInput(SafetyInput):
    title: str = Field(min_length=1, max_length=255)
    activity: str = Field(min_length=1, max_length=10_000)
    apr_id: UUID


class SafetyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    status: str
    requires_nr10: bool
    requires_nr35: bool
    voltage_kv: float | None
    work_height_m: float | None
    risk_level: str
    epi_checklist: dict
    epc_checklist: dict
    hazards: list
    tst_signature: dict | None
    encarregado_signature: dict | None
    valid_from: datetime | None
    valid_until: datetime | None
    released_at: datetime | None


class PermitResponse(SafetyResponse):
    apr_id: UUID
    title: str
    activity: str


def _flags(body: SafetyInput) -> tuple[bool, bool]:
    return (
        body.voltage_kv is not None and body.voltage_kv >= 1.0,
        body.work_height_m is not None and body.work_height_m >= 2.0,
    )


def _validate_release(record: object) -> None:
    nr10 = bool(record.requires_nr10)
    nr35 = bool(record.requires_nr35)
    epi = record.epi_checklist or {}
    epc = record.epc_checklist or {}
    required = (NR10_EPI, NR10_EPC) if nr10 else ((), ())
    required35 = (NR35_EPI, NR35_EPC) if nr35 else ((), ())
    missing = [key for key in (*required[0], *required35[0]) if epi.get(key) is not True]
    missing.extend(key for key in (*required[1], *required35[1]) if epc.get(key) is not True)
    if missing:
        raise HTTPException(
            422, {"message": "Checklist obrigatório incompleto", "missing": missing}
        )
    if not record.tst_signature or not record.encarregado_signature:
        raise HTTPException(422, "APR/PT exige assinatura digital do TST e do Encarregado")
    now = datetime.now(UTC)
    valid_from, valid_until = record.valid_from, record.valid_until
    if valid_from is None or valid_until is None or valid_until <= valid_from or valid_until <= now:
        raise HTTPException(422, "Janela de validade ausente ou expirada")


def _signature(principal, payload: SignatureInput) -> dict:
    if principal.role.value != payload.signer_role:
        raise HTTPException(403, "O papel do token não corresponde ao assinante")
    digest = hashlib.sha256(payload.signature_svg.encode()).hexdigest()
    if digest.lower() != payload.sha256.lower():
        raise HTTPException(422, "sha256 da assinatura não confere")
    signed_at = payload.signed_at.astimezone(UTC)
    return {
        "signer_id": str(principal.user_id),
        "signer_role": payload.signer_role,
        "signed_at": signed_at.isoformat(),
        "sha256": digest,
        "signature_svg": payload.signature_svg,
    }


def _author_hash(body: SafetyInput) -> str:
    raw = body.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@router.post("/aprs", response_model=SafetyResponse, status_code=201)
async def create_apr(body: SafetyInput, db: DB, principal: Principal):
    if principal.role is UserRole.FISCAL:
        raise HTTPException(403, "Fiscal possui acesso somente leitura")
    nr10, nr35 = _flags(body)
    record = APR(
        id=uuid4(),
        company_id=principal.tenant_id,
        project_id=body.project_id,
        parent_id=None,
        observation=body.observation,
        author_id=principal.user_id,
        author_hash=_author_hash(body),
        author_role=principal.role.value,
        client_version=f"server:{int(datetime.now(UTC).timestamp() * 1000)}",
        created_at=datetime.now(UTC),
        requires_nr10=nr10,
        requires_nr35=nr35,
        voltage_kv=body.voltage_kv,
        work_height_m=body.work_height_m,
        risk_level=body.risk_level,
        status="PENDING_SIGNATURE",
        epi_checklist=body.epi_checklist,
        epc_checklist=body.epc_checklist,
        hazards=body.hazards,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
    )
    db.add(record)
    await db.flush()
    return record


@router.get("/aprs", response_model=list[SafetyResponse])
async def list_aprs(db: DB, principal: Principal, project_id: UUID | None = None):
    query = select(APR).where(APR.company_id == principal.tenant_id).order_by(APR.created_at.desc())
    if project_id:
        query = query.where(APR.project_id == project_id)
    return list((await db.scalars(query)).all())


async def _apr(db, principal, record_id: UUID) -> APR:
    record = await db.scalar(
        select(APR).where(APR.id == record_id, APR.company_id == principal.tenant_id)
    )
    if not record:
        raise HTTPException(404, "APR não encontrada")
    return record


@router.get("/aprs/{record_id}", response_model=SafetyResponse)
async def get_apr(record_id: UUID, db: DB, principal: Principal):
    return await _apr(db, principal, record_id)


@router.post("/aprs/{record_id}/signatures", response_model=SafetyResponse)
async def sign_apr(record_id: UUID, body: SignatureInput, db: DB, principal: Principal):
    record = await _apr(db, principal, record_id)
    signed = _signature(principal, body)
    if body.signer_role == "TST":
        record.tst_signature = signed
    else:
        record.encarregado_signature = signed
    await db.flush()
    return record


@router.post("/aprs/{record_id}/release", response_model=SafetyResponse)
async def release_apr(record_id: UUID, db: DB, principal: Principal):
    if principal.role not in {UserRole.DIRETOR, UserRole.ENGENHEIRO_RESIDENTE, UserRole.TST}:
        raise HTTPException(403, "Somente engenharia, diretoria ou TST liberam uma APR")
    record = await _apr(db, principal, record_id)
    _validate_release(record)
    record.status, record.released_at = "RELEASED", datetime.now(UTC)
    await db.flush()
    return record


@router.post("/permits", response_model=PermitResponse, status_code=201)
async def create_permit(body: PermitInput, db: DB, principal: Principal):
    if principal.role is UserRole.FISCAL:
        raise HTTPException(403, "Fiscal possui acesso somente leitura")
    apr = await _apr(db, principal, body.apr_id)
    if apr.project_id != body.project_id:
        raise HTTPException(422, "PT e APR devem pertencer à mesma obra")
    permit_voltage = body.voltage_kv if body.voltage_kv is not None else apr.voltage_kv
    permit_height = body.work_height_m if body.work_height_m is not None else apr.work_height_m
    nr10 = apr.requires_nr10 or (permit_voltage is not None and permit_voltage >= 1.0)
    nr35 = apr.requires_nr35 or (permit_height is not None and permit_height >= 2.0)
    start = body.valid_from or apr.valid_from or datetime.now(UTC)
    end = body.valid_until or apr.valid_until or (start + timedelta(hours=8))
    permit = WorkPermit(
        company_id=principal.tenant_id,
        project_id=body.project_id,
        apr_id=body.apr_id,
        title=body.title,
        activity=body.activity,
        status="PENDING_SIGNATURE",
        voltage_kv=permit_voltage,
        work_height_m=permit_height,
        epi_checklist=body.epi_checklist,
        epc_checklist=body.epc_checklist,
        hazards=body.hazards,
        valid_from=start,
        valid_until=end,
        created_by=principal.user_id,
        risk_level=body.risk_level,
    )
    permit.requires_nr10 = nr10
    permit.requires_nr35 = nr35
    db.add(permit)
    await db.flush()
    return permit


async def _permit(db, principal, record_id: UUID) -> WorkPermit:
    record = await db.scalar(
        select(WorkPermit).where(
            WorkPermit.id == record_id, WorkPermit.company_id == principal.tenant_id
        )
    )
    if not record:
        raise HTTPException(404, "PT não encontrada")
    return record


@router.get("/permits/{record_id}", response_model=PermitResponse)
async def get_permit(record_id: UUID, db: DB, principal: Principal):
    return await _permit(db, principal, record_id)


@router.post("/permits/{record_id}/signatures", response_model=PermitResponse)
async def sign_permit(record_id: UUID, body: SignatureInput, db: DB, principal: Principal):
    permit = await _permit(db, principal, record_id)
    signed = _signature(principal, body)
    if body.signer_role == "TST":
        permit.tst_signature = signed
    else:
        permit.encarregado_signature = signed
    await db.flush()
    return permit


@router.post("/permits/{record_id}/release", response_model=PermitResponse)
async def release_permit(record_id: UUID, db: DB, principal: Principal):
    if principal.role not in {UserRole.DIRETOR, UserRole.ENGENHEIRO_RESIDENTE, UserRole.TST}:
        raise HTTPException(403, "Somente engenharia, diretoria ou TST liberam uma PT")
    permit = await _permit(db, principal, record_id)
    _validate_release(permit)
    permit.status, permit.released_at = "RELEASED", datetime.now(UTC)
    await db.flush()
    return permit
