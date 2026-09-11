// IP — Caramurú Construções — assinatura do autor

import NetInfo, { type NetInfoState } from "@react-native-community/netinfo";

import type { Session } from "../session/credentials";
import { FieldStore } from "../db/store";
import { AuditUploadWorker } from "../audit/uploader";
import { localTables, validatePull, type PullPayload, type PushReceipt } from "./protocol";

export type SyncStatus = "idle" | "syncing" | "offline" | "error";
export type SyncSnapshot = {
  status: SyncStatus;
  pending: number;
  lastError: string | null;
  lastSyncedAt: number | null;
};

type Listener = (snapshot: SyncSnapshot) => void;

export class MobileSync {
  private running: Promise<void> | null = null;
  private unsubscribeNetwork: (() => void) | null = null;
  private listeners = new Set<Listener>();
  private snapshot: SyncSnapshot = { status: "idle", pending: 0, lastError: null, lastSyncedAt: null };
  private connected = true;
  private readonly auditUploads: AuditUploadWorker;

  constructor(private readonly store: FieldStore, private readonly session: Session) {
    this.auditUploads = new AuditUploadWorker(store, session);
  }

  get state(): SyncSnapshot { return this.snapshot; }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.snapshot);
    return () => this.listeners.delete(listener);
  }

  startNetworkListener(): () => void {
    if (this.unsubscribeNetwork) return this.unsubscribeNetwork;
    this.unsubscribeNetwork = NetInfo.addEventListener((state) => {
      const online = Boolean(state.isConnected && state.isInternetReachable !== false);
      const restored = !this.connected && online;
      this.connected = online;
      this.setSnapshot({ status: online ? this.snapshot.status : "offline" });
      if (restored) void this.sync();
    });
    return () => {
      this.unsubscribeNetwork?.();
      this.unsubscribeNetwork = null;
    };
  }

  async sync(): Promise<void> {
    if (this.running) return this.running;
    this.running = this.run().finally(() => { this.running = null; });
    return this.running;
  }

  private async run(): Promise<void> {
    const network = await NetInfo.fetch();
    if (!network.isConnected || network.isInternetReachable === false) {
      this.connected = false;
      await this.refresh("offline");
      return;
    }
    this.connected = true;
    await this.refresh("syncing");
    try {
      const cursor = await this.store.cursor();
      const pull = await this.request<PullPayload>(`/api/v1/sync?last_pulled_at=${cursor}&schema_version=1`);
      await this.store.applyPull(validatePull(pull, cursor));
      await this.auditUploads.run();

      for (const mutation of await this.store.pending()) {
        if (mutation.state !== "pending") continue;
        // Audit photos use the resumable uploads endpoint; keep their local queue
        // visible until the upload worker acknowledges them instead of sending
        // an unsupported table to the Watermelon sync endpoint.
        if (!(localTables as readonly string[]).includes(mutation.tableName)) continue;
        try {
          const receipt = await this.request<PushReceipt>("/api/v1/sync", {
            method: "POST",
            body: mutation.payload,
          });
          if (receipt.batch_id !== mutation.id) throw new Error("Resposta de batch_id divergente.");
          await this.store.acknowledge(mutation.id);
        } catch (error) {
          const status = error instanceof HttpError ? error.status : 0;
          if (status === 409 || status === 422 || status === 403) {
            await this.store.markBlocked(mutation.id, error instanceof Error ? error.message : "Mutação rejeitada");
          } else {
            throw error;
          }
        }
      }

      const finalCursor = await this.store.cursor();
      const finalPull = await this.request<PullPayload>(`/api/v1/sync?last_pulled_at=${finalCursor}&schema_version=1`);
      await this.store.applyPull(validatePull(finalPull, finalCursor));
      await this.refresh("idle");
    } catch (error) {
      await this.refresh("error", error instanceof Error ? error.message : "Falha de sincronização");
    }
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.session.apiUrl.replace(/\/$/, "")}${path}`, {
      ...options,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.session.accessToken}`,
        "X-Tenant-ID": this.session.tenantId,
        ...(options.headers ?? {}),
      },
    });
    if (!response.ok) {
      const text = await response.text();
      throw new HttpError(response.status, text || `HTTP ${response.status}`);
    }
    return response.json() as Promise<T>;
  }

  private async refresh(status: SyncStatus, lastError: string | null = null): Promise<void> {
    this.setSnapshot({ status, pending: await this.store.pendingCount(), lastError, lastSyncedAt: Date.now() });
  }

  private setSnapshot(partial: Partial<SyncSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...partial };
    for (const listener of this.listeners) listener(this.snapshot);
  }
}

export class HttpError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
}

export function networkIsOnline(state: NetInfoState): boolean {
  return Boolean(state.isConnected && state.isInternetReachable !== false);
}
