# IP — Caramurú Construções — assinatura do autor

"""Integration tests use a fresh database and a real NOBYPASSRLS role, never application data."""

import os
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from alembic import command
from alembic.config import Config
from app.core.config import settings
from app.db.session import get_db
from app.main import create_app
from app.models import Company, Project, User
from app.models.project import ProjectType
from app.models.user import UserRole
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_SECRET = "test-only-secret-with-at-least-32-bytes"


@pytest.fixture(autouse=True)
def secure_test_settings(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", TEST_SECRET)
    monkeypatch.setattr(settings, "debug", False)


@pytest.fixture(scope="session")
def database():
    admin_url = os.environ.get("TEST_DATABASE_ADMIN_URL")
    if not admin_url:
        pytest.skip("Set TEST_DATABASE_ADMIN_URL to a PostgreSQL administrator URL")
    admin_url = make_url(admin_url).set(drivername="postgresql+psycopg")
    name = "caramuru_sync_test_" + uuid4().hex
    role = "sync_test_" + uuid4().hex
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    test_url = admin_url.set(database=name)
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
        connection.execute(text(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS'))
    previous = settings.database_url
    try:
        settings.database_url = test_url.render_as_string(hide_password=False)
        config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
        config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
        command.upgrade(config, "head")
        command.check(config)
        engine = create_engine(test_url)
        with engine.begin() as connection:
            connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
            connection.execute(
                text(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                    f'IN SCHEMA public TO "{role}"'
                )
            )
            connection.execute(text(f'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO "{role}"'))
        engine.dispose()
        yield SimpleNamespace(
            url=test_url.set(drivername="postgresql+asyncpg"), role=role, config=config
        )
        # Exercise down/up as well; only the database created above is affected.
        command.downgrade(config, "001_initial")
        command.upgrade(config, "head")
    finally:
        settings.database_url = previous
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
            connection.execute(text(f'DROP ROLE "{role}"'))
        admin.dispose()


@pytest.fixture
async def env(database):
    engine = create_async_engine(database.url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    tenant, other_tenant, project, other_project = uuid4(), uuid4(), uuid4(), uuid4()
    users = {role: uuid4() for role in UserRole}
    other_user = uuid4()
    async with sessions.begin() as db:
        db.add_all(
            [
                Company(id=tenant, name="Test tenant", slug=str(tenant)),
                Company(id=other_tenant, name="Other tenant", slug=str(other_tenant)),
            ]
        )
        await db.flush()
        db.add_all(
            [
                User(
                    id=uid,
                    company_id=tenant,
                    email=f"{role}@test.invalid",
                    full_name=role,
                    role=role,
                    hashed_password="unused",
                )
                for role, uid in users.items()
            ]
        )
        db.add(
            User(
                id=other_user,
                company_id=other_tenant,
                email="other@test.invalid",
                full_name="Other",
                role=UserRole.DIRETOR,
                hashed_password="unused",
            )
        )
        db.add_all(
            [
                Project(
                    id=project,
                    company_id=tenant,
                    code="SE-1",
                    name="Subestação",
                    project_type=ProjectType.SUBESTACAO,
                ),
                Project(
                    id=other_project,
                    company_id=other_tenant,
                    code="SE-2",
                    name="Other",
                    project_type=ProjectType.SUBESTACAO,
                ),
            ]
        )
    app = create_app()

    async def scoped_db():
        async with sessions() as db:
            # Connect as an admin only to SET ROLE; every request then runs without RLS bypass.
            await db.execute(text(f'SET LOCAL ROLE "{database.role}"'))
            yield db

    app.dependency_overrides[get_db] = scoped_db

    def headers(role=UserRole.DIRETOR, tenant_id=tenant, user_id=None, **claims):
        payload = {
            "sub": str(user_id or users[role]),
            "tenant_id": str(tenant_id),
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        } | claims
        token = jwt.encode(payload, settings.secret_key, algorithm="HS256")
        return {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant_id)}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(
            client=client,
            sessions=sessions,
            tenant=tenant,
            other_tenant=other_tenant,
            users=users,
            project=project,
            other_project=other_project,
            headers=headers,
            role=database.role,
            other_user=other_user,
        )
    await engine.dispose()
