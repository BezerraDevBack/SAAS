# IP — Caramurú Construções — assinatura do autor

import time
from uuid import uuid4

import jwt
import pytest
from app.core.config import settings
from app.db.session import get_db
from app.main import create_app
from app.sync.schemas import PushRequest, hlc_key
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError


def test_hlc_numeric_counter_order_and_validation():
    assert hlc_key("1700000000000:000010:A") > hlc_key("1700000000000:000009:Z")
    for invalid in ("yesterday", "1:2:3", "1700000000000:000001:unsafe/node"):
        with pytest.raises(ValueError):
            hlc_key(invalid)


def test_unknown_table_is_rejected():
    with pytest.raises(ValidationError):
        PushRequest.model_validate(
            {
                "batch_id": str(uuid4()),
                "last_pulled_at": 0,
                "changes": {"users": {}},
                "metadata": {},
            }
        )


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "signature",
        "expired",
        "audience",
        "issuer",
        "missing_exp",
        "bad_subject",
        "none_algorithm",
    ],
)
async def test_invalid_auth_fails_before_database_access(fault):
    app = create_app()

    async def no_database():
        # Any SQL access would raise, ensuring invalid credentials never reach tenant queries.
        yield object()

    app.dependency_overrides[get_db] = no_database
    tenant = str(uuid4())
    payload = {
        "sub": str(uuid4()),
        "tenant_id": tenant,
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
        "aud": settings.jwt_audience,
        "iss": settings.jwt_issuer,
    }
    key = settings.secret_key
    if fault == "signature":
        key = "invalid-key-that-is-longer-than-32-bytes"
    if fault == "expired":
        payload["exp"] = int(time.time()) - 10
    if fault == "audience":
        payload["aud"] = "wrong"
    if fault == "issuer":
        payload["iss"] = "wrong"
    if fault == "missing_exp":
        del payload["exp"]
    if fault == "bad_subject":
        payload["sub"] = "invalid"
    token = jwt.encode(
        payload,
        key if fault != "none_algorithm" else "",
        algorithm="HS256" if fault != "none_algorithm" else "none",
    )
    headers = {"X-Tenant-ID": tenant}
    if fault != "missing":
        headers["Authorization"] = f"Bearer {token}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/sync", headers=headers)
        assert response.status_code == 401


async def test_health_docs_and_openapi_contract():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/docs")).status_code == 200
    schema = app.openapi()
    sync = schema["paths"]["/api/v1/sync"]
    assert set(sync) == {"get", "post"}
    assert sync["post"]["security"] == [{"HTTPBearer": []}]
