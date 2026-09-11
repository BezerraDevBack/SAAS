// IP — Caramurú Construções — assinatura do autor

/* eslint-disable react-hooks/exhaustive-deps */
import { CameraView, useCameraPermissions, type CameraView as CameraViewType } from "expo-camera";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";

import { useFieldRuntime } from "../src/runtime";
import { buildWatermark, compressWebp, sha256File, validateCameraMetadata, type AuditCaptureMetadata } from "../src/audit/photo";

type Captured = { uri: string; metadata: AuditCaptureMetadata };

export default function AuditCamera() {
  const router = useRouter();
  const { project_id: projectId } = useLocalSearchParams<{ project_id?: string }>();
  const { runtime } = useFieldRuntime();
  const [permission, requestPermission] = useCameraPermissions();
  const camera = useRef<CameraViewType>(null);
  const frame = useRef<View>(null);
  const [captured, setCaptured] = useState<Captured | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("A câmera é obrigatória; galeria desabilitada.");

  useEffect(() => {
    if (!captured || !runtime) return;
    let active = true;
    const timer = setTimeout(() => void (async () => {
      try {
        setBusy(true);
        // react-native-view-shot rasterizes the image plus this text overlay,
        // so the watermark is part of the pixels sent to the server.
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const { captureRef } = require("react-native-view-shot") as { captureRef: (ref: View, options: object) => Promise<string> };
        const stampedUri = await captureRef(frame.current as View, { format: "jpg", quality: 0.95, result: "tmpfile" });
        const compressed = await compressWebp(stampedUri);
        validateCameraMetadata(captured.metadata);
        const hash = await sha256File(compressed.uri);
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const fs = require("expo-file-system") as { getInfoAsync: (uri: string) => Promise<{ size?: number }> };
        const info = await fs.getInfoAsync(compressed.uri);
        const photoId = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
        const activeProject = projectId ?? String((await runtime.store.database.get("projects").query().fetch())[0]?._raw.id ?? "");
        if (!activeProject) throw new Error("Abra a câmera a partir de uma obra ativa.");
        await runtime.store.enqueueAuditPhoto({
          id: photoId, project_id: activeProject, local_uri: captured.uri,
          compressed_uri: compressed.uri, content_type: "image/webp", size_bytes: info.size ?? 0, sha256: hash,
          latitude: captured.metadata.latitude, longitude: captured.metadata.longitude, accuracy_m: captured.metadata.accuracyM,
          gnss_timestamp: captured.metadata.gnssTimestamp, captured_at: captured.metadata.capturedAt,
          watermark_text: captured.metadata.watermarkText, width: compressed.width ?? 0, height: compressed.height ?? 0,
        });
        if (active) setMessage("Foto carimbada e enfileirada para upload seguro.");
      } catch (error) {
        if (active) setMessage(error instanceof Error ? error.message : "Falha ao preparar a foto.");
      } finally { if (active) setBusy(false); }
    })(), 80);
    return () => { active = false; clearTimeout(timer); };
  }, [captured, runtime]);

  const takePhoto = async () => {
    if (!camera.current || !runtime) return;
    try {
      setBusy(true);
      // Location is loaded directly from the hardware provider; no manual coordinate input.
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const Location = require("expo-location") as { requestForegroundPermissionsAsync: () => Promise<{ status: string }>; getCurrentPositionAsync: (options: object) => Promise<{ coords: { latitude: number; longitude: number; accuracy: number | null }; timestamp: number }> };
      const permissionResult = await Location.requestForegroundPermissionsAsync();
      if (permissionResult.status !== "granted") throw new Error("Permissão GNSS é obrigatória para auditoria.");
      const position = await Location.getCurrentPositionAsync({ accuracy: 6 });
      const picture = await camera.current.takePictureAsync({ quality: 1, skipProcessing: false });
      if (!picture?.uri) throw new Error("A câmera não retornou uma imagem.");
      const gnssTimestamp = new Date(position.timestamp).toISOString();
      const metadata: AuditCaptureMetadata = {
        obra: "Obra ativa", latitude: position.coords.latitude, longitude: position.coords.longitude,
        accuracyM: position.coords.accuracy ?? 9999, gnssTimestamp, capturedAt: new Date().toISOString(),
        watermarkText: buildWatermark("Obra ativa", position.coords.latitude, position.coords.longitude, position.coords.accuracy ?? 9999, gnssTimestamp),
      };
      setCaptured({ uri: picture.uri, metadata });
      setMessage("Carimbando coordenadas e comprimindo em WebP…");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Falha na captura."); setBusy(false); }
  };

  if (!permission) return <View style={styles.center}><ActivityIndicator /></View>;
  if (!permission.granted) return <View style={styles.center}><Text style={styles.title}>Câmera de auditoria</Text><Text style={styles.message}>A seleção da galeria é proibida. Autorize a câmera para continuar.</Text><Pressable style={styles.button} onPress={requestPermission}><Text style={styles.buttonText}>AUTORIZAR CÂMERA</Text></Pressable></View>;
  return <View style={styles.root}>
    {!captured ? <CameraView ref={camera} style={styles.camera} facing="back" /> : <View ref={frame} collapsable={false} style={styles.preview}><Image source={{ uri: captured.uri }} style={styles.previewImage} /><Text style={styles.watermark}>{captured.metadata.watermarkText}</Text></View>}
    <View style={styles.panel}><Text style={styles.message}>{message}</Text><Pressable disabled={busy} style={styles.button} onPress={() => void takePhoto()}><Text style={styles.buttonText}>{busy ? "PROCESSANDO…" : "CAPTURAR E ENFILEIRAR"}</Text></Pressable><Pressable style={styles.back} onPress={() => router.back()}><Text style={styles.backText}>VOLTAR</Text></Pressable></View>
  </View>;
}

const styles = StyleSheet.create({ root: { flex: 1, backgroundColor: "#000" }, camera: { flex: 1 }, preview: { flex: 1, backgroundColor: "#111", justifyContent: "center" }, previewImage: { width: "100%", height: "80%", resizeMode: "contain" }, watermark: { color: "#fff", backgroundColor: "#000c", fontSize: 15, padding: 12 }, panel: { padding: 16, gap: 12, backgroundColor: "#000" }, center: { flex: 1, padding: 24, justifyContent: "center", gap: 18, backgroundColor: "#07111f" }, title: { color: "#fff", fontSize: 28, fontWeight: "800" }, message: { color: "#fff", fontSize: 16, lineHeight: 23 }, button: { minHeight: 56, paddingHorizontal: 18, borderRadius: 10, alignItems: "center", justifyContent: "center", backgroundColor: "#f5c542" }, buttonText: { color: "#111", fontSize: 16, fontWeight: "900" }, back: { minHeight: 48, alignItems: "center", justifyContent: "center" }, backText: { color: "#fff", fontWeight: "800" }, });
