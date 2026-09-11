// IP — Caramurú Construções — assinatura do autor

export const localTables = ["projects", "assets", "inspections", "apr_records"] as const;
export type LocalTable = (typeof localTables)[number];
export type RemoteTable = "projects" | "assets" | "inspections" | "aprs";
export type Primitive = string | number | boolean | null;
export type JsonValue = Primitive | JsonValue[] | { [field: string]: JsonValue };
export type RawRecord = { id: string; [field: string]: JsonValue };
export type TableChanges = { created: RawRecord[]; updated: RawRecord[]; deleted: string[] };

export type PushPayload = {
  batch_id: string;
  last_pulled_at: number;
  changes: Partial<Record<RemoteTable, TableChanges>>;
  metadata: Partial<Record<RemoteTable, Record<string, {
    client_version: string;
    changed_fields: string[];
  }>>>;
};

export type PullPayload = {
  changes: Record<RemoteTable, TableChanges>;
  timestamp: number;
};

export type PushReceipt = {
  batch_id: string;
  applied: number;
  conflicts: { table_name: RemoteTable; record_id: string; rejected_fields: string[] }[];
  requires_pull: boolean;
};

export const toRemote = (table: LocalTable): RemoteTable => table === "apr_records" ? "aprs" : table;
export const toLocal = (table: RemoteTable): LocalTable => table === "aprs" ? "apr_records" : table;
export const emptyChanges = (): TableChanges => ({ created: [], updated: [], deleted: [] });
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function validatePull(value: unknown, previousCursor: number): PullPayload {
  const result = value as PullPayload;
  if (!result || !Number.isSafeInteger(result.timestamp) || result.timestamp < previousCursor || !result.changes) {
    throw new Error("Resposta de sincronização inválida; cursor local preservado.");
  }
  for (const localTable of localTables) {
    const changes = result.changes[toRemote(localTable)];
    if (!changes || !Array.isArray(changes.created) || !Array.isArray(changes.updated) || !Array.isArray(changes.deleted)) {
      throw new Error("Tabelas incompletas na resposta de sincronização.");
    }
    const ids = new Set<string>();
    const rows = [...changes.created, ...changes.updated, ...changes.deleted.map((id) => ({ id }))];
    for (const row of rows) {
      if (!row || typeof row.id !== "string" || !UUID.test(row.id) || ids.has(row.id)) {
        throw new Error("Identificador inválido ou duplicado no pull.");
      }
      const validJson = (value: unknown): value is JsonValue => {
        if (value === null || ["string", "number", "boolean"].includes(typeof value)) return true;
        if (Array.isArray(value)) return value.every(validJson);
        return typeof value === "object" && Object.values(value as Record<string, unknown>).every(validJson);
      };
      if (Object.values(row).some((value) => !validJson(value))) {
        throw new Error("Registro inválido no pull.");
      }
      ids.add(row.id);
    }
  }
  return result;
}
