// IP — Caramurú Construções — assinatura do autor

import { Database, Model, Q } from "@nozbe/watermelondb";

import { Asset, AuditPhoto, Mutation, SyncState } from "./models";
import {
  emptyChanges,
  localTables,
  toLocal,
  toRemote,
  type LocalTable,
  type PullPayload,
  type JsonValue,
  type PushPayload,
  type RawRecord,
} from "../sync/protocol";

type Operation = "created" | "updated" | "deleted";
type AnyRecord = Record<string, JsonValue>;

const writableFields: Record<LocalTable, string[]> = {
  projects: ["code", "name", "project_type", "status", "description", "voltage_kv", "geometry"],
  assets: ["name", "asset_type", "serial_number", "qr_code", "status", "project_id", "manufacturer", "notes"],
  inspections: ["project_id", "parent_id", "observation"],
  apr_records: ["project_id", "parent_id", "observation", "requires_nr10", "requires_nr35", "voltage_kv", "work_height_m", "risk_level", "status", "epi_checklist", "epc_checklist", "hazards", "tst_signature", "encarregado_signature", "valid_from", "valid_until", "released_at"],
};

const jsonFields = new Set(["epi_checklist", "epc_checklist", "hazards", "tst_signature", "encarregado_signature"]);
const localValue = (key: string, value: JsonValue): unknown => {
  if (jsonFields.has(key) && value !== null && typeof value !== "string") return JSON.stringify(value);
  if ((key === "voltage_kv" || key === "work_height_m") && typeof value === "number") return String(value);
  return value;
};

const collectionFor = (database: Database, table: string): any => database.get(table as never);
const rawValue = (model: Model, field: string): any => (model._raw as Record<string, any>)[field];
const fallbackId = (): string => {
  const bytes = Array.from({ length: 16 }, () => Math.floor(Math.random() * 256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  return bytes.map((byte, index) => (index === 4 || index === 6 || index === 8 || index === 10 ? "-" : "") + byte.toString(16).padStart(2, "0")).join("");
};

function setFields(record: Model, values: AnyRecord): void {
  for (const [key, value] of Object.entries(values)) {
    if (key !== "id" && key !== "_status" && key !== "_changed") {
      record._setRaw(key, localValue(key, value) as any);
    }
  }
}

function operationRows(payload: PushPayload): { table: LocalTable; operation: Operation; row: AnyRecord }[] {
  const result: { table: LocalTable; operation: Operation; row: AnyRecord }[] = [];
  for (const [remoteName, tableChanges] of Object.entries(payload.changes)) {
    if (!tableChanges) continue;
    const table = toLocal(remoteName as "projects" | "assets" | "inspections" | "aprs");
    for (const row of tableChanges.created) result.push({ table, operation: "created", row });
    for (const row of tableChanges.updated) result.push({ table, operation: "updated", row });
    for (const id of tableChanges.deleted) result.push({ table, operation: "deleted", row: { id } });
  }
  return result;
}

export class FieldStore {
  constructor(
    readonly database: Database,
    private readonly makeId: () => string = fallbackId,
    private readonly clock: () => number = Date.now,
  ) {}

  async initialize(): Promise<void> {
    const states = await collectionFor(this.database, "sync_state").query().fetch();
    if (states.length > 0) return;
    await this.database.write(async () => {
      await this.database.batch(collectionFor(this.database, "sync_state").prepareCreateFromDirtyRaw({
        id: "state", cursor: 0, last_synced_at: 0, hlc_wall: 0, hlc_counter: 0,
        sequence: 0, node_id: this.makeId(), _status: "synced", _changed: "",
      }));
    });
  }

  async state(): Promise<SyncState> {
    return this.database.get<SyncState>("sync_state").find("state");
  }

  async cursor(): Promise<number> { return Number(rawValue(await this.state(), "cursor")); }

  async pending(): Promise<Mutation[]> {
    return this.database.get<Mutation>("mutation_queue").query(Q.sortBy("sequence", Q.asc)).fetch();
  }

  async pendingCount(): Promise<number> {
    // Blocked mutations still require field reconciliation and must remain visible to the crew.
    return this.database.get<Mutation>("mutation_queue").query().fetchCount();
  }

  async enqueueAuditPhoto(values: AnyRecord): Promise<string> {
    if (!values.id || !values.project_id || !values.local_uri) throw new Error("Foto sem metadados obrigatórios.");
    return this.database.write(async () => {
      const state = await this.state();
      const id = String(values.id);
      const queueId = this.makeId();
      const sequence = Number(rawValue(state, "sequence")) + 1;
      const local = this.database.get<AuditPhoto>("audit_photos").prepareCreateFromDirtyRaw({
        ...Object.fromEntries(Object.entries(values).map(([key, value]) => [key, localValue(key, value)])),
        upload_status: "pending", upload_offset: 0, _status: "synced", _changed: "",
      });
      const queue = collectionFor(this.database, "mutation_queue").prepareCreateFromDirtyRaw({
        id: queueId, table_name: "audit_photos", record_id: id, payload: JSON.stringify({ kind: "audit_photo", photo: values }),
        state: "pending", error: null, sequence, created_at: this.clock(), _status: "synced", _changed: "",
      });
      await this.database.batch(local, queue, state.prepareUpdate((record: Model) => setFields(record, { sequence })));
      return queueId;
    });
  }

  async findAssetByQr(qrCode: string): Promise<Asset | null> {
    const rows = await this.database.get<Asset>("assets").query(Q.where("qr_code", qrCode.trim())).fetch();
    return rows[0] ?? null;
  }

  async enqueue(table: LocalTable, operation: Exclude<Operation, "deleted">, values: RawRecord): Promise<string> {
    if (!values.id || !writableFields[table].length) throw new Error("Mutação sem identificador.");
    if (table === "inspections" || table === "apr_records") {
      if (operation !== "created") throw new Error("Revisões são imutáveis; crie uma nova revisão.");
    }
    const keys = Object.keys(values).filter((key) => key !== "id");
    if (!keys.length || keys.some((key) => !writableFields[table].includes(key))) throw new Error("Campo de mutação inválido.");

    return this.database.write(async () => {
      const currentState = await this.state();
      const current = await collectionFor(this.database, table).query(Q.where("id", values.id)).fetch();
      if (operation === "updated" && !current[0]) throw new Error("Registro não encontrado localmente.");
      if (operation === "created" && current[0]) throw new Error("ID já existe localmente.");

      const oldWall = Number(rawValue(currentState, "hlc_wall"));
      let wall = Math.max(this.clock(), oldWall, Number(rawValue(currentState, "cursor")));
      let counter = wall === oldWall ? Number(rawValue(currentState, "hlc_counter")) + 1 : 0;
      if (counter > 999999) { wall += 1; counter = 0; }
      const clientVersion = `${String(wall).padStart(13, "0")}:${String(counter).padStart(6, "0")}:${rawValue(currentState, "node_id")}`;
      const remote = toRemote(table);
      const changes = emptyChanges();
      if (operation === "created") changes.created.push(values);
      else changes.updated.push(values);
      const batchId = this.makeId();
      const payload: PushPayload = {
        batch_id: batchId,
        last_pulled_at: Number(rawValue(currentState, "cursor")),
        changes: { [remote]: changes },
        metadata: {
          [remote]: {
            [values.id]: {
              client_version: clientVersion,
              changed_fields: operation === "updated" ? keys : [],
            },
          },
        },
      };

      const domainRecord = current[0]
        ? current[0].prepareUpdate((record: Model) => setFields(record, values))
        : collectionFor(this.database, table).prepareCreateFromDirtyRaw({
            ...Object.fromEntries(Object.entries(values).map(([key, value]) => [key, localValue(key, value)])),
            created_at: this.clock(), updated_at: this.clock(), _status: "synced", _changed: "",
          });
      const sequence = Number(rawValue(currentState, "sequence")) + 1;
      const queueRecord = collectionFor(this.database, "mutation_queue").prepareCreateFromDirtyRaw({
        id: batchId,
        table_name: table,
        record_id: values.id,
        payload: JSON.stringify(payload),
        state: "pending",
        error: null,
        sequence,
        created_at: this.clock(),
        _status: "synced",
        _changed: "",
      });
      const stateUpdate = currentState.prepareUpdate((record: Model) => setFields(record, {
        hlc_wall: wall, hlc_counter: counter, sequence,
      }));
      await this.database.batch(domainRecord, queueRecord, stateUpdate);
      return batchId;
    });
  }

  async enqueueDelete(table: LocalTable, id: string): Promise<string> {
    return this.database.write(async () => {
      const state = await this.state();
      const batchId = this.makeId();
      const remote = toRemote(table);
      const hlc = this.nextHlc(state);
      const payload: PushPayload = {
        batch_id: batchId,
        last_pulled_at: Number(rawValue(state, "cursor")),
        changes: { [remote]: { created: [], updated: [], deleted: [id] } },
        metadata: { [remote]: { [id]: { client_version: hlc.version, changed_fields: [] } } },
      };
      const sequence = Number(rawValue(state, "sequence")) + 1;
      await this.database.batch(
        collectionFor(this.database, "mutation_queue").prepareCreateFromDirtyRaw({
          id: batchId, table_name: table, record_id: id, payload: JSON.stringify(payload), state: "pending",
          error: null, sequence, created_at: this.clock(), _status: "synced", _changed: "",
        }),
        state.prepareUpdate((record: Model) => setFields(record, {
          sequence, hlc_wall: hlc.wall, hlc_counter: hlc.counter,
        })),
      );
      return batchId;
    });
  }

  private nextHlc(state: SyncState): { version: string; wall: number; counter: number } {
    const wall = Math.max(this.clock(), Number(rawValue(state, "hlc_wall")));
    const counter = wall === Number(rawValue(state, "hlc_wall")) ? Number(rawValue(state, "hlc_counter")) + 1 : 0;
    return {
      version: `${String(wall).padStart(13, "0")}:${String(counter).padStart(6, "0")}:${rawValue(state, "node_id")}`,
      wall,
      counter,
    };
  }

  async acknowledge(batchId: string): Promise<void> {
    await this.database.write(async () => {
      const row = await this.database.get<Mutation>("mutation_queue").find(batchId);
      await this.database.batch(row.prepareDestroyPermanently());
    });
  }

  async acknowledgePhoto(queueId: string, photoId: string, uploadId: string, offset: number): Promise<void> {
    await this.database.write(async () => {
      const queue = await this.database.get<Mutation>("mutation_queue").find(queueId);
      const photo = await this.database.get<AuditPhoto>("audit_photos").find(photoId);
      await this.database.batch(
        photo.prepareUpdate((record: Model) => setFields(record, { upload_status: "uploaded", upload_id: uploadId, upload_offset: offset })),
        queue.prepareDestroyPermanently(),
      );
    });
  }

  async markBlocked(batchId: string, message: string): Promise<void> {
    await this.database.write(async () => {
      const row = await this.database.get<Mutation>("mutation_queue").find(batchId);
      await this.database.batch(row.prepareUpdate((record: Model) => setFields(record, { state: "blocked", error: message })));
    });
  }

  async applyPull(value: PullPayload): Promise<void> {
    await this.database.write(async () => {
      const state = await this.state();
      const previousCursor = Number(rawValue(state, "cursor"));
      const pull = value;
      if (!Number.isSafeInteger(pull.timestamp) || pull.timestamp < previousCursor) throw new Error("Cursor de pull inválido.");
      const pending = await this.pending();
      const operations: Model[] = [];
      for (const localTable of localTables) {
        const changes = pull.changes[toRemote(localTable)];
        if (!changes) throw new Error(`Tabela ausente: ${toRemote(localTable)}`);
        for (const incoming of [...changes.created, ...changes.updated]) {
          const localPending = pending.filter((item) => item.tableName === localTable && item.recordId === incoming.id);
          const merged = { ...incoming } as AnyRecord;
          for (const item of localPending) {
            const queued = operationRows(JSON.parse(item.payload) as PushPayload).find((row) => row.table === localTable && row.row.id === incoming.id);
            if (queued) Object.assign(merged, queued.row);
          }
          const current = await collectionFor(this.database, localTable).query(Q.where("id", incoming.id)).fetch();
          if (current[0]) operations.push(current[0].prepareUpdate((record: Model) => setFields(record, merged)));
          else operations.push(collectionFor(this.database, localTable).prepareCreateFromDirtyRaw({ ...merged, _status: "synced", _changed: "" }));
        }
        for (const id of changes.deleted) {
          if (pending.some((item) => item.tableName === localTable && item.recordId === id)) continue;
          const current = await collectionFor(this.database, localTable).query(Q.where("id", id)).fetch();
          if (current[0]) operations.push(current[0].prepareDestroyPermanently());
        }
      }
      operations.push(state.prepareUpdate((record: Model) => setFields(record, {
        cursor: pull.timestamp, last_synced_at: this.clock(),
      })));
      await this.database.batch(...operations);
    });
  }
}
