// IP — Caramurú Construções — assinatura do autor

import * as SecureStore from "expo-secure-store";

export type Session = {
  accessToken: string;
  apiUrl: string;
  tenantId: string;
  userId: string;
};

const SESSION_KEY = "caramuru.session.v1";

function validSession(value: unknown): value is Session {
  if (!value || typeof value !== "object") return false;
  const session = value as Partial<Session>;
  return [session.accessToken, session.apiUrl, session.tenantId, session.userId]
    .every((item) => typeof item === "string" && item.length > 0);
}

export async function loadSession(): Promise<Session | null> {
  const encoded = await SecureStore.getItemAsync(SESSION_KEY);
  if (!encoded) return null;
  try {
    const value: unknown = JSON.parse(encoded);
    return validSession(value) ? value : null;
  } catch {
    return null;
  }
}

export async function saveSession(session: Session): Promise<void> {
  if (!validSession(session)) throw new Error("Sessão incompleta.");
  await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(session), {
    keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK,
  });
}

export async function clearSession(): Promise<void> {
  await SecureStore.deleteItemAsync(SESSION_KEY);
}
