// IP — Caramurú Construções — assinatura do autor

import { Link } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";

import { useFieldRuntime } from "../src/runtime";

export default function HomeScreen() {
  const { runtime, snapshot, loading, error } = useFieldRuntime();
  const [message, setMessage] = useState<string | null>(null);
  const isOffline = snapshot.status === "offline";
  const statusLabel = isOffline
    ? `MODO OFFLINE (${snapshot.pending} dados pendentes de envio)`
    : snapshot.status === "syncing" ? "SINCRONIZANDO..." : snapshot.status === "error" ? "FALHA DE SINCRONIZAÇÃO" : "SINCRONIZADO";

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={[styles.status, isOffline ? styles.offline : styles.online]}>
          <View style={styles.statusDot} />
          <Text style={styles.statusText}>{statusLabel}</Text>
        </View>
        <Text style={styles.eyebrow}>CARAMURÚ CONSTRUÇÕES</Text>
        <Text style={styles.title}>Campo</Text>
        <Text style={styles.subtitle}>Obras e equipamentos no seu ritmo, mesmo sem sinal.</Text>

        {loading && <Text style={styles.info}>Abrindo banco local...</Text>}
        {error && <Text style={styles.warning}>{error} Entre com uma sessão para sincronizar.</Text>}
        {snapshot.lastError && <Text style={styles.warning}>{snapshot.lastError}</Text>}

        <Link href="/qr" asChild>
          <Pressable style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]} accessibilityRole="button">
            <Text style={styles.primaryButtonText}>LER QR DO EQUIPAMENTO</Text>
            <Text style={styles.buttonHint}>Curvadora · Guincho · Andaime</Text>
          </Pressable>
        </Link>
        <Link href="/release" asChild>
          <Pressable style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]} accessibilityRole="button">
            <Text style={styles.primaryButtonText}>LIBERAÇÃO DIÁRIA APR / PT</Text>
            <Text style={styles.buttonHint}>Checklist NR-10 · NR-35 · assinaturas</Text>
          </Pressable>
        </Link>
        <Link href="/audit" asChild>
          <Pressable style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]} accessibilityRole="button">
            <Text style={styles.secondaryButtonText}>CÂMERA DE AUDITORIA</Text>
          </Pressable>
        </Link>
        <Pressable
          style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}
          disabled={!runtime}
          onPress={() => { void runtime?.sync.sync(); setMessage("Sincronização solicitada."); }}
          accessibilityRole="button"
        >
          <Text style={styles.secondaryButtonText}>SINCRONIZAR AGORA</Text>
        </Pressable>
        {message && <Text style={styles.info}>{message}</Text>}

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Fila local</Text>
          <Text style={styles.cardValue}>{snapshot.pending}</Text>
          <Text style={styles.cardBody}>alterações protegidas no aparelho até a conexão voltar</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0b1220" },
  content: { flexGrow: 1, padding: 22, gap: 18 },
  status: { minHeight: 54, borderRadius: 10, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", gap: 12 },
  online: { backgroundColor: "#0d6b4d" },
  offline: { backgroundColor: "#a63b19" },
  statusDot: { width: 14, height: 14, borderRadius: 7, backgroundColor: "#fff" },
  statusText: { color: "#fff", fontSize: 15, fontWeight: "800", letterSpacing: 0.4, flexShrink: 1 },
  eyebrow: { color: "#f2c14e", fontSize: 13, fontWeight: "800", letterSpacing: 1.8, marginTop: 18 },
  title: { color: "#fff", fontSize: 46, fontWeight: "900", lineHeight: 52 },
  subtitle: { color: "#d7e0ed", fontSize: 19, lineHeight: 27, maxWidth: 500 },
  info: { color: "#b8c6d9", fontSize: 16, lineHeight: 23 },
  warning: { color: "#ffd6bd", backgroundColor: "#5d2518", padding: 14, borderRadius: 8, fontSize: 16, lineHeight: 23 },
  primaryButton: { minHeight: 82, borderRadius: 12, backgroundColor: "#f2c14e", padding: 18, justifyContent: "center" },
  primaryButtonText: { color: "#1b2534", fontWeight: "900", fontSize: 18, letterSpacing: 0.3 },
  buttonHint: { color: "#26354b", fontSize: 14, marginTop: 5 },
  secondaryButton: { minHeight: 58, borderRadius: 12, borderWidth: 2, borderColor: "#f2c14e", justifyContent: "center", alignItems: "center" },
  secondaryButtonText: { color: "#f2c14e", fontWeight: "900", fontSize: 16 },
  pressed: { opacity: 0.7 },
  card: { borderRadius: 12, backgroundColor: "#172337", padding: 18, marginTop: "auto" },
  cardTitle: { color: "#d7e0ed", fontSize: 16, fontWeight: "800" },
  cardValue: { color: "#fff", fontSize: 40, fontWeight: "900", marginTop: 5 },
  cardBody: { color: "#a9b8cb", fontSize: 15, lineHeight: 22 },
});
