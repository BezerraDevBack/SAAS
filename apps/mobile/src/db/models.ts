// IP — Caramurú Construções — assinatura do autor

import { Model } from "@nozbe/watermelondb";

const value = (model: Model, field: string): unknown => (model._raw as Record<string, unknown>)[field];

export class Project extends Model {
  static table = "projects";
  get name() { return String(value(this, "name")); }
  get code() { return String(value(this, "code")); }
}

export class Asset extends Model {
  static table = "assets";
  get name() { return String(value(this, "name")); }
  get status() { return String(value(this, "status")); }
  get assetType() { return String(value(this, "asset_type")); }
  get qrCode() { return String(value(this, "qr_code")); }
  get serialNumber() { return String(value(this, "serial_number")); }
  get projectId() { return value(this, "project_id") as string | null; }
}

export class Inspection extends Model { static table = "inspections"; }
export class AprRecord extends Model { static table = "apr_records"; }
export class AuditPhoto extends Model {
  static table = "audit_photos";
  get uploadStatus() { return String(value(this, "upload_status")); }
  get localUri() { return String(value(this, "local_uri")); }
}

export class Mutation extends Model {
  static table = "mutation_queue";
  get payload() { return String(value(this, "payload")); }
  get state() { return String(value(this, "state")); }
  get error() { return value(this, "error") as string | null; }
  get recordId() { return String(value(this, "record_id")); }
  get tableName() { return String(value(this, "table_name")); }
}

export class SyncState extends Model { static table = "sync_state"; }

export const modelClasses = [Project, Asset, Inspection, AprRecord, AuditPhoto, Mutation, SyncState];
