// IP — Caramurú Construções — assinatura do autor

import assert from "node:assert/strict";

process.env["NODE_ENV"] = "test";

const ids = [
  "00000000-0000-4000-8000-000000000001",
  "00000000-0000-4000-8000-000000000002",
  "00000000-0000-4000-8000-000000000003",
];
async function main() {
  const { default: SQLiteAdapter } = await import("@nozbe/watermelondb/adapters/sqlite");
  const { Database } = await import("@nozbe/watermelondb");
  const { modelClasses } = await import("../src/db/models");
  const { schema } = await import("../src/db/schema");
  const { FieldStore } = await import("../src/db/store");
  const { toLocal, toRemote, validatePull } = await import("../src/sync/protocol");
  let nextId = 0;
  const store = new FieldStore(
    new Database({ adapter: new SQLiteAdapter({ schema, dbName: undefined, jsi: false }), modelClasses }),
    () => ids[nextId++] ?? `00000000-0000-4000-8000-${String(nextId).padStart(12, "0")}`,
    () => 1_700_000_000_000,
  );

  await store.initialize();
  const projectId = ids[0];
  await store.enqueue("projects", "created", {
    id: projectId, code: "SE-TEST", name: "Subestação de teste",
    project_type: "SUBESTACAO", status: "PLANEJAMENTO",
  });
  assert.equal(await store.pendingCount(), 1, "a domain write creates one durable outbox item");
  assert.equal((await store.database.get("projects").query().fetch()).length, 1);
  const queued = await store.pending();
  assert.equal(JSON.parse(queued[0].payload).batch_id, queued[0].id, "batch_id is stable in the persisted payload");
  assert.equal(await store.cursor(), 0, "cursor does not move when only local data was written");
  await store.enqueue("apr_records", "created", {
    id: ids[1], project_id: projectId, parent_id: null, observation: "APR offline",
    requires_nr10: true, requires_nr35: false, voltage_kv: 13.8, work_height_m: null,
    risk_level: "HIGH", status: "PENDING_SIGNATURE", epi_checklist: { luvas_isolantes: true },
    epc_checklist: { bloqueio_etiquetagem: true }, hazards: [], tst_signature: { sha256: "x" },
    encarregado_signature: { sha256: "y" }, valid_from: "2026-09-10T08:00:00Z", valid_until: "2026-09-10T16:00:00Z", released_at: null,
  });
  const apr = await store.database.get("apr_records").find(ids[1]);
  assert.equal((apr._raw as Record<string, unknown>).epi_checklist, JSON.stringify({ luvas_isolantes: true }));
  await store.enqueueAuditPhoto({
    id: ids[2], project_id: projectId, local_uri: "/tmp/capture.jpg", compressed_uri: "/tmp/capture.webp",
    object_key: null, content_type: "image/webp", size_bytes: 600_000, sha256: "a".repeat(64),
    latitude: -23.5, longitude: -46.6, accuracy_m: 3, gnss_timestamp: "2026-09-10T12:00:00Z",
    captured_at: "2026-09-10T12:00:01Z", watermark_text: "LAT: -23.500000 | UTC: 2026-09-10T12:00:00Z",
    width: 1920, height: 1080, upload_offset: 0, error: null,
  });
  assert.equal((await store.database.get("audit_photos").query().fetch()).length, 1);
  assert.equal((await store.pending()).filter(item => item.tableName === "audit_photos").length, 1);
  assert.equal(toRemote("apr_records"), "aprs");
  assert.equal(toLocal("aprs"), "apr_records");
  assert.throws(() => validatePull({ changes: {}, timestamp: 20 }, 0), /Tabelas incompletas/);
  console.log("mobile persistence checks passed");
}

void main();
