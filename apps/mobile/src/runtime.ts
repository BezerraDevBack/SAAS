// IP — Caramurú Construções — assinatura do autor

import { useEffect, useState } from "react";

import { openFieldStore } from "./db";
import { FieldStore } from "./db/store";
import { loadSession, type Session } from "./session/credentials";
import { MobileSync, type SyncSnapshot } from "./sync/client";

export type FieldRuntime = {
  session: Session;
  store: FieldStore;
  sync: MobileSync;
};

export function useFieldRuntime(): {
  runtime: FieldRuntime | null;
  snapshot: SyncSnapshot;
  loading: boolean;
  error: string | null;
} {
  const [runtime, setRuntime] = useState<FieldRuntime | null>(null);
  const [snapshot, setSnapshot] = useState<SyncSnapshot>({ status: "offline", pending: 0, lastError: null, lastSyncedAt: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let stopNetwork: (() => void) | undefined;
    let stopSubscription: (() => void) | undefined;
    void (async () => {
      try {
        const session = await loadSession();
        if (!session) {
          if (active) { setLoading(false); setError("Sessão de campo ainda não configurada."); }
          return;
        }
        const store = await openFieldStore(session);
        const sync = new MobileSync(store, session);
        stopSubscription = sync.subscribe((value) => active && setSnapshot(value));
        stopNetwork = sync.startNetworkListener();
        if (active) { setRuntime({ session, store, sync }); setLoading(false); }
        await sync.sync();
      } catch (cause) {
        if (active) { setLoading(false); setError(cause instanceof Error ? cause.message : "Falha ao abrir o banco local."); }
      }
    })();
    return () => {
      active = false;
      stopNetwork?.();
      stopSubscription?.();
    };
  }, []);

  return { runtime, snapshot, loading, error };
}
