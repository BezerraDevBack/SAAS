// IP — Caramurú Construções — assinatura do autor

import * as Crypto from "expo-crypto";

export type AuditCaptureMetadata = {
  obra: string;
  latitude: number;
  longitude: number;
  accuracyM: number;
  gnssTimestamp: string;
  capturedAt: string;
  watermarkText: string;
};

/** The source is always CameraView; there is deliberately no picker/gallery path. */
export function buildWatermark(obra: string, latitude: number, longitude: number, accuracyM: number, gnssTimestamp: string): string {
  return `OBRA: ${obra} | LAT: ${latitude.toFixed(6)} | LON: ${longitude.toFixed(6)} | PRECISÃO: ${accuracyM.toFixed(1)} m | UTC: ${new Date(gnssTimestamp).toISOString()}`;
}

export async function compressWebp(uri: string): Promise<{ uri: string; width?: number; height?: number }> {
  // Expo's native image manipulator performs this work off the JS UI path.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const manipulator = require("expo-image-manipulator") as {
    SaveFormat: { WEBP: string };
    manipulateAsync: (path: string, actions: unknown[], options: { compress: number; format: string; base64: boolean }) => Promise<{ uri: string; width: number; height: number }>;
  };
  const result = await manipulator.manipulateAsync(uri, [], {
    compress: 0.82,
    format: manipulator.SaveFormat.WEBP,
    base64: false,
  });
  return { uri: result.uri, width: result.width, height: result.height };
}

export async function sha256File(uri: string): Promise<string> {
  // Hash the decoded bytes, never the base64 envelope, so the digest matches
  // the server's streaming SHA-256 validation at upload completion.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const FileSystem = require("expo-file-system") as { readAsStringAsync: (path: string, options: { encoding: string }) => Promise<string> };
  const base64 = await FileSystem.readAsStringAsync(uri, { encoding: "base64" });
  const binary = atob(base64);
  const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
  const digest = new Uint8Array(await Crypto.digest(Crypto.CryptoDigestAlgorithm.SHA256, bytes));
  return Array.from(digest, byte => byte.toString(16).padStart(2, "0")).join("");
}

export function validateCameraMetadata(metadata: AuditCaptureMetadata): void {
  if (!Number.isFinite(metadata.latitude) || !Number.isFinite(metadata.longitude) || !Number.isFinite(metadata.accuracyM)) {
    throw new Error("A evidência precisa de coordenadas GNSS válidas.");
  }
  if (metadata.accuracyM < 0 || metadata.accuracyM > 5_000) throw new Error("Precisão GNSS inválida.");
  if (!metadata.watermarkText.includes("UTC") || !metadata.watermarkText.includes("LAT:")) {
    throw new Error("A foto precisa conter carimbo de coordenadas e UTC.");
  }
}
