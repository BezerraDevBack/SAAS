// IP — Caramurú Construções — assinatura do autor

import { CameraView, useCameraPermissions, type BarcodeScanningResult } from "expo-camera";
import { Link } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useCallback, useState } from "react";
import { Pressable, SafeAreaView, StyleSheet, Text, View } from "react-native";

import { useFieldRuntime } from "../src/runtime";

export default function QrScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const { runtime, error: runtimeError } = useFieldRuntime();
  const [scanned, setScanned] = useState(false);
  const [result, setResult] = useState<{ name: string; type: string; status: string } | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const onBarcodeScanned = useCallback(async ({ data }: BarcodeScanningResult) => {
    if (scanned) return;
    setScanned(true);
    if (!runtime) { setMessage("Sessão local ainda não está disponível."); return; }
    const asset = await runtime.store.findAssetByQr(data);
    if (!asset) { setMessage(`Nenhum equipamento encontrado para ${data}.`); return; }
    setResult({ name: asset.name, type: asset.assetType, status: asset.status });
  }, [runtime, scanned]);

  if (!permission?.granted) {
    return (
      <SafeAreaView style={styles.safe}>
        <StatusBar style="light" />
        <View style={styles.center}>
          <Text style={styles.title}>Leitura de QR</Text>
          <Text style={styles.body}>{permission?.canAskAgain === false ? "A câmera foi bloqueada nas configurações do aparelho." : "Autorize a câmera para identificar o equipamento."}</Text>
          {permission?.canAskAgain !== false && <Pressable style={styles.primary} onPress={() => void requestPermission()}><Text style={styles.primaryText}>AUTORIZAR CÂMERA</Text></Pressable>}
          <Link href="/" asChild><Pressable style={styles.secondary}><Text style={styles.secondaryText}>VOLTAR</Text></Pressable></Link>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />
      <View style={styles.header}><Link href="/" asChild><Pressable style={styles.back}><Text style={styles.backText}>‹ VOLTAR</Text></Pressable></Link><Text style={styles.headerTitle}>QR EQUIPAMENTO</Text></View>
      <View style={styles.cameraFrame}>
        <CameraView
          style={StyleSheet.absoluteFill}
          facing="back"
          barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
          onBarcodeScanned={scanned ? undefined : onBarcodeScanned}
        />
        <View style={styles.scanTarget}><View style={styles.corner} /><View style={[styles.corner, styles.cornerTr]} /><View style={[styles.corner, styles.cornerBl]} /><View style={[styles.corner, styles.cornerBr]} /></View>
        <Text style={styles.scanHint}>Aponte para o QR Code do ativo</Text>
      </View>
      {runtimeError && <Text style={styles.body}>{runtimeError}</Text>}
      {message && <Text style={styles.warning}>{message}</Text>}
      {result && <View style={styles.result}><Text style={styles.resultKicker}>EQUIPAMENTO IDENTIFICADO</Text><Text style={styles.resultTitle}>{result.name}</Text><Text style={styles.body}>{result.type} · {result.status}</Text></View>}
      {scanned && <Pressable style={styles.primary} onPress={() => { setScanned(false); setResult(null); setMessage(null); }}><Text style={styles.primaryText}>LER OUTRO QR</Text></Pressable>}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0b1220", padding: 18 },
  center: { flex: 1, justifyContent: "center", gap: 18 },
  header: { minHeight: 54, flexDirection: "row", alignItems: "center", gap: 16 },
  back: { minHeight: 48, justifyContent: "center" },
  backText: { color: "#f2c14e", fontSize: 16, fontWeight: "900" },
  headerTitle: { color: "#fff", fontSize: 18, fontWeight: "900" },
  title: { color: "#fff", fontSize: 32, fontWeight: "900" },
  body: { color: "#d7e0ed", fontSize: 17, lineHeight: 25 },
  cameraFrame: { flex: 1, minHeight: 360, maxHeight: 600, overflow: "hidden", borderRadius: 14, backgroundColor: "#182539", justifyContent: "center", alignItems: "center" },
  scanTarget: { width: 230, height: 230, position: "relative" },
  corner: { position: "absolute", left: 0, top: 0, width: 42, height: 42, borderLeftWidth: 5, borderTopWidth: 5, borderColor: "#f2c14e" },
  cornerTr: { left: undefined, right: 0, borderLeftWidth: 0, borderRightWidth: 5 },
  cornerBl: { top: undefined, bottom: 0, borderTopWidth: 0, borderBottomWidth: 5 },
  cornerBr: { left: undefined, top: undefined, right: 0, bottom: 0, borderLeftWidth: 0, borderTopWidth: 0, borderRightWidth: 5, borderBottomWidth: 5 },
  scanHint: { position: "absolute", bottom: 20, color: "#fff", backgroundColor: "#000b", padding: 10, fontSize: 16, fontWeight: "700" },
  primary: { minHeight: 58, borderRadius: 11, backgroundColor: "#f2c14e", justifyContent: "center", alignItems: "center", padding: 14 },
  primaryText: { color: "#1b2534", fontSize: 17, fontWeight: "900" },
  secondary: { minHeight: 58, borderRadius: 11, borderWidth: 2, borderColor: "#f2c14e", justifyContent: "center", alignItems: "center", padding: 14 },
  secondaryText: { color: "#f2c14e", fontSize: 17, fontWeight: "900" },
  warning: { color: "#ffd6bd", backgroundColor: "#5d2518", borderRadius: 8, padding: 13, fontSize: 16 },
  result: { backgroundColor: "#172337", borderRadius: 12, padding: 18, gap: 6 },
  resultKicker: { color: "#f2c14e", fontSize: 13, fontWeight: "900", letterSpacing: 1 },
  resultTitle: { color: "#fff", fontSize: 27, fontWeight: "900" },
});
