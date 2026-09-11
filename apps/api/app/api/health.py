# IP — Caramurú Construções — assinatura do autor

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter(tags=["health"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    service: str = "caramuru-api"
    timestamp: datetime


class ReadinessResponse(BaseModel):
    status: str
    database: str
    timestamp: datetime


@router.get("/health", response_model=HealthResponse, summary="Liveness")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(UTC),
    )


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness (PostgreSQL)")
async def readiness(db: DbSession) -> ReadinessResponse:
    await db.execute(text("SELECT 1"))
    return ReadinessResponse(
        status="ok",
        database="ok",
        timestamp=datetime.now(UTC),
    )
