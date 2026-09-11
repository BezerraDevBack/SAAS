// IP — Caramurú Construções — assinatura do autor

import { Database } from "@nozbe/watermelondb";
import SQLiteAdapter from "@nozbe/watermelondb/adapters/sqlite";
import * as Crypto from "expo-crypto";

import type { Session } from "../session/credentials";
import { modelClasses } from "./models";
import { schema } from "./schema";
import { FieldStore } from "./store";

const openStores = new Map<string, Promise<FieldStore>>();

export async function openFieldStore(session: Session): Promise<FieldStore> {
  const scope = JSON.stringify([session.apiUrl, session.tenantId, session.userId]);
  const existing = openStores.get(scope);
  if (existing) return existing;

  const opening = (async () => {
    const digest = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, scope);
    const adapter = new SQLiteAdapter({
      dbName: `caramuru_field_${digest.slice(0, 32)}`,
      schema,
      jsi: true,
      onSetUpError: (error) => console.error("WatermelonDB setup failed", error),
    });
    await adapter.initializingPromise;
    if (adapter._dispatcherType !== "jsi") {
      throw new Error("SQLite JSI indisponível; gere um development build nativo.");
    }
    const store = new FieldStore(new Database({ adapter, modelClasses }));
    await store.initialize();
    return store;
  })();
  openStores.set(scope, opening);
  opening.catch(() => openStores.delete(scope));
  return opening;
}

export async function closeFieldStore(session: Session): Promise<void> {
  const scope = JSON.stringify([session.apiUrl, session.tenantId, session.userId]);
  openStores.delete(scope);
}
