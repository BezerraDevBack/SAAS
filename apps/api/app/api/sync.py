# IP — Caramurú Construções — assinatura do autor

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.auth import DB, Principal
from app.sync.schemas import PullResponse, PushRequest, PushResponse
from app.sync.service import pull, push

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


@router.get("", response_model=PullResponse)
async def pull_changes(
    db: DB,
    principal: Principal,
    last_pulled_at: Annotated[int, Query(ge=0, le=9007199254740991)] = 0,
    schema_version: Literal[1] = 1,
    migration: Literal["null"] | None = None,
):
    """Consistent tenant delta. V1 supports schema 1, without schema migrations."""
    response = await pull(db, principal, last_pulled_at)
    await db.commit()
    return response


@router.post("", response_model=PushResponse)
async def push_changes(body: PushRequest, db: DB, principal: Principal):
    """Atomically apply a durable mutation batch; replay the same batch_id after network failure."""
    try:
        response = await push(db, principal, body)
        await db.commit()
        return response
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Mutation violates a record constraint; pull and retry") from exc
    except DBAPIError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) in ("40001", "40P01"):
            raise HTTPException(409, "Concurrent transaction; retry the same batch") from exc
        raise
