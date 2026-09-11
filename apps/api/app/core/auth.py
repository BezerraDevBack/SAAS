# IP — Caramurú Construções — assinatura do autor

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.company import Company
from app.models.user import User, UserRole

ROLE_RANK = {
    UserRole.FISCAL: 1,
    UserRole.ENCARREGADO: 2,
    UserRole.TST: 3,
    UserRole.ENGENHEIRO_RESIDENTE: 4,
    UserRole.DIRETOR: 5,
}
bearer = HTTPBearer(auto_error=False)
DB = Annotated[AsyncSession, Depends(get_db)]


@dataclass(frozen=True)
class TenantPrincipal:
    tenant_id: UUID
    user_id: UUID
    role: UserRole


async def get_principal(
    db: DB,
    x_tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> TenantPrincipal:
    if not credentials:
        raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    # Never accept a known scaffold secret, even in debug mode. No development auth bypass.
    if len(settings.secret_key) < 32 or settings.secret_key == "change-me-in-production":
        raise HTTPException(503, "JWT signing key is not configured")
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "tenant_id", "iss", "aud"]},
        )
        tenant_id, user_id = UUID(claims["tenant_id"]), UUID(claims["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(401, "Invalid token", headers={"WWW-Authenticate": "Bearer"}) from exc
    if tenant_id != x_tenant_id:
        raise HTTPException(403, "Tenant does not match token")
    # Transaction-local: automatically cleared on commit/rollback and safe for pooled connections.
    await db.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
    )
    user = await db.scalar(
        select(User)
        .join(Company, Company.id == User.company_id)
        .where(
            User.id == user_id,
            User.company_id == tenant_id,
            User.is_active.is_(True),
            Company.is_active.is_(True),
        )
    )
    if user is None:
        raise HTTPException(403, "Inactive or unavailable membership")
    # Role is read from the database; a stale or forged role claim cannot elevate privileges.
    await db.execute(
        text("SELECT set_config('app.author_rank', :rank, true)"),
        {"rank": str(ROLE_RANK[user.role])},
    )
    return TenantPrincipal(tenant_id, user.id, user.role)


Principal = Annotated[TenantPrincipal, Depends(get_principal)]
