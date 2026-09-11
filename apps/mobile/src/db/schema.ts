// IP — Caramurú Construções — assinatura do autor

import { appSchema, tableSchema, type ColumnSchema } from "@nozbe/watermelondb";

const stringColumn = (name: string, isOptional = false, isIndexed = false): ColumnSchema => ({
  name,
  type: "string",
  isOptional,
  isIndexed,
});

const revisionColumns: ColumnSchema[] = [
  stringColumn("project_id", false, true),
  stringColumn("parent_id", true, true),
  stringColumn("observation"),
  stringColumn("author_id", true),
  stringColumn("author_role", true),
  stringColumn("author_hash", true),
  stringColumn("client_version", true),
  { name: "created_at", type: "number" },
];

const aprSafetyColumns: ColumnSchema[] = [
  { name: "requires_nr10", type: "boolean" }, { name: "requires_nr35", type: "boolean" },
  stringColumn("voltage_kv", true), stringColumn("work_height_m", true), stringColumn("risk_level", false),
  stringColumn("status", false), stringColumn("epi_checklist", false), stringColumn("epc_checklist", false),
  stringColumn("hazards", false), stringColumn("tst_signature", true), stringColumn("encarregado_signature", true),
  stringColumn("valid_from", true), stringColumn("valid_until", true), stringColumn("released_at", true),
];

/** JSI requires a native development/release build; Expo Go is not supported. */
export const schema = appSchema({
  version: 1,
  tables: [
    tableSchema({
      name: "projects",
      columns: [
        stringColumn("code", false, true), stringColumn("name"), stringColumn("project_type"),
        stringColumn("status"), stringColumn("description", true), stringColumn("voltage_kv", true),
        stringColumn("geometry", true), { name: "created_at", type: "number" },
        { name: "updated_at", type: "number" },
      ],
    }),
    tableSchema({
      name: "assets",
      columns: [
        stringColumn("name"), stringColumn("asset_type"), stringColumn("serial_number"),
        stringColumn("qr_code", false, true), stringColumn("status"), stringColumn("project_id", true, true),
        stringColumn("manufacturer", true), stringColumn("notes", true),
        { name: "created_at", type: "number" }, { name: "updated_at", type: "number" },
      ],
    }),
    tableSchema({ name: "inspections", columns: revisionColumns }),
    tableSchema({ name: "apr_records", columns: [...revisionColumns, ...aprSafetyColumns] }),
    tableSchema({
      name: "audit_photos",
      columns: [stringColumn("project_id", false, true), stringColumn("apr_id", true, true), stringColumn("work_permit_id", true, true),
        stringColumn("local_uri"), stringColumn("compressed_uri", true), stringColumn("object_key", true), stringColumn("content_type"),
        { name: "size_bytes", type: "number" }, stringColumn("sha256"), { name: "latitude", type: "number" },
        { name: "longitude", type: "number" }, { name: "accuracy_m", type: "number" }, stringColumn("gnss_timestamp"),
        stringColumn("captured_at"), stringColumn("watermark_text"), stringColumn("upload_status"), stringColumn("upload_id", true),
        { name: "upload_offset", type: "number" }, { name: "width", type: "number", isOptional: true },
        { name: "height", type: "number", isOptional: true }, stringColumn("error", true),
      ],
    }),
    tableSchema({
      name: "mutation_queue",
      columns: [stringColumn("table_name"), stringColumn("record_id", false, true), stringColumn("payload"),
        stringColumn("state", false, true), stringColumn("error", true), { name: "sequence", type: "number" },
        { name: "created_at", type: "number" }],
    }),
    tableSchema({
      name: "sync_state",
      columns: [{ name: "cursor", type: "number" }, { name: "last_synced_at", type: "number" },
        { name: "hlc_wall", type: "number" }, { name: "hlc_counter", type: "number" },
        { name: "sequence", type: "number" }, stringColumn("node_id")],
    }),
  ],
});
