// IP — Caramurú Construções — assinatura do autor

import type { Session } from "../session/credentials";
import { FieldStore } from "../db/store";

type UploadStart = { upload_id: string; photo_id: string; offset: number; length: number; chunk_size: number };

/** Resumes queued audit photos without involving the Watermelon sync envelope. */
export class AuditUploadWorker {
  constructor(private readonly store: FieldStore, private readonly session: Session) {}

  async run(): Promise<void> {
    for (const mutation of await this.store.pending()) {
      if (mutation.tableName !== "audit_photos" || mutation.state !== "pending") continue;
      const payload = JSON.parse(mutation.payload) as { kind: string; photo: Record<string, unknown> };
      if (payload.kind !== "audit_photo") continue;
      await this.upload(mutation.id, String(payload.photo.id), payload.photo);
    }
  }

  private async upload(queueId: string, photoId: string, photo: Record<string, unknown>): Promise<void> {
    const base = this.session.apiUrl.replace(/\/$/, "");
    const headers = { Authorization: `Bearer ${this.session.accessToken}`, "X-Tenant-ID": this.session.tenantId };
    const startResponse = await fetch(`${base}/api/v1/uploads`, {
      method: "POST", headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ photo_id: photoId, project_id: photo.project_id, apr_id: photo.apr_id ?? null, work_permit_id: photo.work_permit_id ?? null, size_bytes: photo.size_bytes, sha256: photo.sha256, content_type: photo.content_type, latitude: photo.latitude, longitude: photo.longitude, accuracy_m: photo.accuracy_m, gnss_timestamp: photo.gnss_timestamp, captured_at: photo.captured_at, watermark_text: photo.watermark_text, width: photo.width, height: photo.height }),
    });
    if (!startResponse.ok) throw new Error(`Upload init HTTP ${startResponse.status}`);
    const start = await startResponse.json() as UploadStart;
    const fileResponse = await fetch(String(photo.compressed_uri));
    if (!fileResponse.ok) throw new Error("Arquivo WebP local indisponível");
    const bytes = new Uint8Array(await fileResponse.arrayBuffer());
    let offset = start.offset;
    while (offset < bytes.byteLength) {
      const chunk = bytes.slice(offset, Math.min(offset + start.chunk_size, bytes.byteLength));
      const response = await fetch(`${base}/api/v1/uploads/${start.upload_id}`, {
        method: "PATCH", headers: { ...headers, "Content-Type": "application/offset+octet-stream", "Upload-Offset": String(offset) }, body: chunk,
      });
      if (!response.ok) throw new Error(`Upload chunk HTTP ${response.status}`);
      offset = Number(response.headers.get("Upload-Offset") ?? offset + chunk.byteLength);
    }
    const complete = await fetch(`${base}/api/v1/uploads/${start.upload_id}/complete`, { method: "POST", headers });
    if (!complete.ok) throw new Error(`Upload complete HTTP ${complete.status}`);
    await this.store.acknowledgePhoto(queueId, photoId, start.upload_id, offset);
  }
}
