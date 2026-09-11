# IP — Caramurú Construções — assinatura do autor

import asyncio
import copy
import time
from uuid import uuid4

import pytest
from app.models import APR, Asset, Inspection, SyncBatch, SyncChange, User
from app.models.user import UserRole
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

URL = "/api/v1/sync"


def asset(**overrides):
    rid = str(uuid4())
    return {
        "id": rid,
        "name": "Guincho",
        "asset_type": "GUINCHO",
        "serial_number": rid,
        "qr_code": rid,
        **overrides,
    }


def batch(table, row, operation="created", cursor=0, clock=None, fields=None):
    rid = row["id"]
    return {
        "batch_id": str(uuid4()),
        "last_pulled_at": cursor,
        "changes": {table: {operation: [rid if operation == "deleted" else row]}},
        "metadata": {
            table: {
                rid: {
                    "client_version": clock or f"{int(time.time() * 1000):013d}:000001:deviceA",
                    "changed_fields": fields or [],
                }
            }
        },
    }


async def get_pull(env, cursor=0, **kwargs):
    response = await env.client.get(
        URL, params={"last_pulled_at": cursor}, headers=env.headers(**kwargs)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def send(env, payload, expected=200, **kwargs):
    response = await env.client.post(URL, json=payload, headers=env.headers(**kwargs))
    assert response.status_code == expected, response.text
    return response


async def test_initial_pull_cursor_and_tenant_isolation(env):
    response = await get_pull(env)
    assert [r["id"] for r in response["changes"]["projects"]["created"]] == [str(env.project)]
    assert response["timestamp"] > 0
    again = await get_pull(env, response["timestamp"])
    assert again["timestamp"] > response["timestamp"]
    assert all(not rows for table in again["changes"].values() for rows in table.values())
    assert "company_id" not in response["changes"]["projects"]["created"][0]


async def test_create_update_delete_delta_and_fold(env):
    cursor = (await get_pull(env))["timestamp"]
    row = asset(project_id=str(env.project))
    await send(env, batch("assets", row, cursor=cursor))
    created = await get_pull(env, cursor)
    assert len(created["changes"]["assets"]["created"]) == 1
    updated = {"id": row["id"], "status": "EM_USO"}
    await send(env, batch("assets", updated, "updated", created["timestamp"], fields=["status"]))
    folded = await get_pull(env, cursor)
    assert folded["changes"]["assets"]["created"][0]["status"] == "EM_USO"
    assert not folded["changes"]["assets"]["updated"]
    delta = await get_pull(env, created["timestamp"])
    assert len(delta["changes"]["assets"]["updated"]) == 1
    await send(env, batch("assets", row, "deleted", delta["timestamp"]))
    deleted = await get_pull(env, delta["timestamp"])
    assert deleted["changes"]["assets"]["deleted"] == [row["id"]]
    assert not (await get_pull(env))["changes"]["assets"]["deleted"]
    await send(env, batch("assets", row, cursor=deleted["timestamp"]), expected=409)


async def test_durable_batch_replay_and_payload_mismatch(env):
    payload = batch("assets", asset())
    first = await send(env, payload)
    second = await send(env, payload)
    assert first.json() == second.json()
    async with env.sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(SyncChange)
                .where(SyncChange.tenant_id == env.tenant, SyncChange.table_name == "assets")
            )
            == 1
        )
    altered = copy.deepcopy(payload)
    altered["changes"]["assets"]["created"][0]["name"] = "Different"
    await send(env, altered, expected=409)


async def test_concurrent_duplicate_retry_commits_once(env):
    payload = batch("assets", asset())
    results = await asyncio.gather(send(env, payload), send(env, payload))
    assert results[0].json() == results[1].json()
    async with env.sessions() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(Asset).where(Asset.company_id == env.tenant)
            )
            == 1
        )


async def test_concurrent_insert_same_id_different_data(env):
    first = asset()
    second = first | {"name": "Conflicting create"}
    results = await asyncio.gather(
        *[
            env.client.post(URL, json=batch("assets", row), headers=env.headers())
            for row in (first, second)
        ]
    )
    assert sorted(r.status_code for r in results) == [200, 409]


@pytest.mark.parametrize("high_first", [False, True])
async def test_field_merge_hierarchy_independent_of_arrival_order(env, high_first):
    row = asset()
    await send(env, batch("assets", row))
    cursor = (await get_pull(env))["timestamp"]
    wall = int(time.time() * 1000)
    high = batch(
        "assets",
        {"id": row["id"], "status": "MANUTENCAO"},
        "updated",
        cursor,
        clock=f"{wall:013d}:000001:high",
        fields=["status"],
    )
    low = batch(
        "assets",
        {"id": row["id"], "status": "EM_USO", "notes": "Inspecionado"},
        "updated",
        cursor,
        clock=f"{wall:013d}:000002:low",
        fields=["status", "notes"],
    )
    writes = [(high, UserRole.DIRETOR), (low, UserRole.ENCARREGADO)]
    if not high_first:
        writes.reverse()
    responses = [await send(env, p, role=r) for p, r in writes]
    final = (await get_pull(env, cursor))["changes"]["assets"]["updated"][0]
    assert final["status"] == "MANUTENCAO"
    assert final["notes"] == "Inspecionado"
    if high_first:
        assert responses[1].json()["conflicts"][0]["rejected_fields"] == ["status"]
    # A causally later edit is allowed after observing the director's change.
    next_cursor = (await get_pull(env))["timestamp"]
    await send(
        env,
        batch(
            "assets",
            {"id": row["id"], "status": "DISPONIVEL"},
            "updated",
            next_cursor,
            fields=["status"],
        ),
        role=UserRole.ENCARREGADO,
    )
    assert (await get_pull(env, next_cursor))["changes"]["assets"]["updated"][0][
        "status"
    ] == "DISPONIVEL"


async def test_equal_role_uses_hlc_and_explicit_field_mask(env):
    row = asset()
    await send(env, batch("assets", row))
    cursor = (await get_pull(env))["timestamp"]
    wall = int(time.time() * 1000)
    newer = batch(
        "assets",
        {"id": row["id"], "status": "MANUTENCAO"},
        "updated",
        cursor,
        clock=f"{wall:013d}:000010:B",
        fields=["status"],
    )
    stale = batch(
        "assets",
        {"id": row["id"], "status": "EM_USO", "notes": "keep"},
        "updated",
        cursor,
        clock=f"{wall:013d}:000009:A",
        fields=["status", "notes"],
    )
    await send(env, newer)
    response = await send(env, stale)
    assert response.json()["conflicts"][0]["rejected_fields"] == ["status"]
    value = (await get_pull(env, cursor))["changes"]["assets"]["updated"][0]
    assert (value["status"], value["notes"]) == ("MANUTENCAO", "keep")


@pytest.mark.parametrize("high_first", [False, True])
async def test_explicit_same_value_edit_keeps_higher_priority(env, high_first):
    row = asset(status="DISPONIVEL")
    await send(env, batch("assets", row))
    cursor = (await get_pull(env))["timestamp"]
    high = batch(
        "assets",
        {"id": row["id"], "status": "DISPONIVEL"},
        "updated",
        cursor,
        fields=["status"],
    )
    low = batch(
        "assets",
        {"id": row["id"], "status": "EM_USO"},
        "updated",
        cursor,
        fields=["status"],
    )
    writes = [(high, UserRole.DIRETOR), (low, UserRole.ENCARREGADO)]
    if not high_first:
        writes.reverse()
    for payload, role in writes:
        await send(env, payload, role=role)
    final = (await get_pull(env, cursor))["changes"]["assets"]["updated"]
    assert final[0]["status"] == "DISPONIVEL"


@pytest.mark.parametrize("table,model", [("inspections", Inspection), ("aprs", APR)])
async def test_append_only_revisions_preserve_author_and_concurrent_branches(env, table, model):
    root = {"id": str(uuid4()), "project_id": str(env.project), "observation": "Original"}
    payload = batch(table, root)
    await send(env, payload, role=UserRole.TST)
    await send(env, payload, role=UserRole.TST)
    children = [
        {
            "id": str(uuid4()),
            "project_id": str(env.project),
            "parent_id": root["id"],
            "observation": note,
        }
        for note in ("Observation A", "Observation B")
    ]
    await asyncio.gather(*[send(env, batch(table, child), role=UserRole.TST) for child in children])
    data = (await get_pull(env))["changes"][table]["created"]
    assert len(data) == 3
    assert len({r["author_hash"] for r in data}) == 3
    assert all(r["author_id"] == str(env.users[UserRole.TST]) for r in data)
    await send(
        env,
        batch(table, root | {"observation": "Overwrite"}, "updated", fields=["observation"]),
        expected=409,
    )
    await send(env, batch(table, root, "deleted"), expected=409)
    async with env.sessions() as db:
        with pytest.raises(DBAPIError):
            await db.execute(
                text(f"UPDATE {table} SET observation = 'tampered' WHERE id = :id"),
                {"id": root["id"]},
            )
        await db.rollback()
        original = await db.get(model, root["id"])
        assert original.observation == "Original"


async def test_batch_failure_rolls_back_records_journal_and_receipt(env):
    good, bad = asset(), asset(project_id=str(env.other_project))
    payload = batch("assets", good)
    other = batch("assets", bad)
    payload["changes"]["assets"]["created"].append(bad)
    payload["metadata"]["assets"].update(other["metadata"]["assets"])
    await send(env, payload, expected=422)
    async with env.sessions() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(Asset).where(Asset.company_id == env.tenant)
            )
            == 0
        )
        assert (
            await db.scalar(
                select(func.count()).select_from(SyncBatch).where(SyncBatch.tenant_id == env.tenant)
            )
            == 0
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(SyncChange)
                .where(SyncChange.tenant_id == env.tenant, SyncChange.table_name == "assets")
            )
            == 0
        )


async def test_rls_without_context_and_cross_tenant_sql(env):
    async with env.sessions() as db:
        await db.execute(text(f'SET LOCAL ROLE "{env.role}"'))
        assert await db.scalar(select(func.count()).select_from(User)) == 0
        await db.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(env.tenant)}
        )
        assert await db.scalar(select(func.count()).select_from(User)) == 5
        with pytest.raises(DBAPIError):
            await db.execute(
                text(
                    "INSERT INTO projects(id,company_id,code,name,project_type) "
                    "VALUES(:id,:t,'X','escape','SUBESTACAO')"
                ),
                {"id": uuid4(), "t": env.other_tenant},
            )
        await db.rollback()


async def test_cross_tenant_header_references_and_body_forgery(env):
    headers = env.headers()
    headers["X-Tenant-ID"] = str(env.other_tenant)
    assert (await env.client.get(URL, headers=headers)).status_code == 403
    await send(env, batch("assets", asset(company_id=str(env.other_tenant))), expected=422)
    await send(env, batch("assets", asset(project_id=str(env.other_project))), expected=422)
    await send(
        env,
        batch(
            "projects", {"id": str(env.other_project), "name": "attack"}, "updated", fields=["name"]
        ),
        expected=422,
    )


async def test_rbac_database_role_wins_over_jwt_role_claim(env):
    await get_pull(env, role=UserRole.FISCAL)
    await send(env, batch("assets", asset()), expected=403, role=UserRole.FISCAL)
    # Calling headers directly permits an untrusted role claim in the signed token.
    headers = env.headers(role=UserRole.FISCAL)
    import jwt
    from app.core.config import settings

    payload = jwt.decode(headers["Authorization"].split()[1], options={"verify_signature": False})
    payload["role"] = "DIRETOR"
    headers["Authorization"] = "Bearer " + jwt.encode(
        payload, settings.secret_key, algorithm="HS256"
    )
    assert (
        await env.client.post(URL, json=batch("assets", asset()), headers=headers)
    ).status_code == 403


async def test_stale_project_update_and_future_cursor_rejected(env):
    before = (await get_pull(env))["timestamp"]
    row = {"id": str(env.project), "name": "First"}
    await send(env, batch("projects", row, "updated", before, fields=["name"]))
    await send(
        env,
        batch("projects", row | {"name": "Stale"}, "updated", before, fields=["name"]),
        expected=409,
    )
    response = await env.client.get(
        URL, params={"last_pulled_at": 9007199254740991}, headers=env.headers()
    )
    assert response.status_code == 409


async def test_external_sql_write_is_captured(env):
    cursor = (await get_pull(env))["timestamp"]
    async with env.sessions.begin() as db:
        await db.execute(
            text("UPDATE projects SET name = 'SQL update' WHERE id = :id"), {"id": env.project}
        )
    result = await get_pull(env, cursor)
    assert result["changes"]["projects"]["updated"][0]["name"] == "SQL update"


async def test_pull_waits_for_uncommitted_writer_without_losing_event(env):
    cursor = (await get_pull(env))["timestamp"]
    async with env.sessions() as writer:
        await writer.execute(
            text("UPDATE projects SET name = 'Uncommitted' WHERE id = :id"), {"id": env.project}
        )
        pulling = asyncio.create_task(get_pull(env, cursor))
        try:
            await asyncio.sleep(0.15)
            assert not pulling.done()
            await writer.commit()
            response = await asyncio.wait_for(pulling, timeout=5)
        finally:
            if not pulling.done():
                pulling.cancel()
    assert response["changes"]["projects"]["updated"][0]["name"] == "Uncommitted"
    next_pull = await get_pull(env, response["timestamp"])
    assert not next_pull["changes"]["projects"]["updated"]


async def test_geometry_round_trip_and_no_watermelon_internal_fields(env):
    row = {
        "id": str(uuid4()),
        "code": "GEO",
        "name": "Geo",
        "project_type": "SUBESTACAO",
        "geometry": '{"type":"Point","coordinates":[-46.6,-23.5]}',
        "_status": "created",
        "_changed": "name",
    }
    await send(env, batch("projects", row))
    records = (await get_pull(env))["changes"]["projects"]["created"]
    record = next(r for r in records if r["id"] == row["id"])
    assert isinstance(record["geometry"], str)
    assert isinstance(record["created_at"], int)
    assert "_status" not in record and "_changed" not in record
