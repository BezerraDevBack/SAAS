// IP — Caramurú Construções — assinatura do autor

import * as Crypto from "expo-crypto";
import { useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";

import { SignaturePad } from "../src/safety/SignaturePad";
import { useFieldRuntime } from "../src/runtime";

const NR10_EPI = ["capacete_classe_b", "oculos_protecao", "luvas_isolantes", "luvas_cobertura", "vestimenta_anti_arco", "calcado_isolante", "detector_tensao"];
const NR10_EPC = ["barreira_sinalizacao", "aterramento_temporario", "bloqueio_etiquetagem", "delimitacao_area"];
const NR35_EPI = ["cinturao_paraquedista", "talabarte_duplo", "trava_quedas", "capacete_jugular"];
const NR35_EPC = ["linha_vida", "ponto_ancoragem", "guarda_corpo", "plano_resgate"];

export default function DailyRelease() {
  const router = useRouter();
  const { project_id: projectId } = useLocalSearchParams<{ project_id?: string }>();
  const { runtime } = useFieldRuntime();
  const [observation, setObservation] = useState("");
  const [voltage, setVoltage] = useState("");
  const [height, setHeight] = useState("");
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [tst, setTst] = useState("");
  const [encarregado, setEncarregado] = useState("");
  const [message, setMessage] = useState("Preencha o checklist e as duas assinaturas.");
  const nr10 = Number(voltage) >= 1;
  const nr35 = Number(height) >= 2;
  const required = useMemo(() => [...(nr10 ? [...NR10_EPI, ...NR10_EPC] : []), ...(nr35 ? [...NR35_EPI, ...NR35_EPC] : [])], [nr10, nr35]);
  const complete = required.every(key => checked[key]) && Boolean(tst) && Boolean(encarregado) && Boolean(observation.trim());

  const sign = async (role: "TST" | "ENCARREGADO", svg: string) => {
    const sha256 = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, svg);
    const value = JSON.stringify({ signer_role: role, signed_at: new Date().toISOString(), sha256, signature_svg: svg });
    if (role === "TST") setTst(value);
    else setEncarregado(value);
  };
  const submit = async () => {
    const activeProject = projectId ?? String((await runtime?.store.database.get("projects").query().fetch())?.[0]?._raw.id ?? "");
    if (!runtime || !activeProject || !complete) { setMessage("Checklist, obra, observação e assinaturas são obrigatórios."); return; }
    const id = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-apr`;
    const now = new Date();
    await runtime.store.enqueue("apr_records", "created", {
      id, project_id: activeProject, parent_id: null, observation, requires_nr10: nr10, requires_nr35: nr35,
      voltage_kv: Number(voltage) || null, work_height_m: Number(height) || null, risk_level: nr10 || nr35 ? "HIGH" : "MEDIUM",
      status: "PENDING_SIGNATURE", epi_checklist: Object.fromEntries(required.filter(k => NR10_EPI.includes(k) || NR35_EPI.includes(k)).map(k => [k, true])),
      epc_checklist: Object.fromEntries(required.filter(k => NR10_EPC.includes(k) || NR35_EPC.includes(k)).map(k => [k, true])), hazards: [],
      tst_signature: JSON.parse(tst), encarregado_signature: JSON.parse(encarregado), valid_from: now.toISOString(), valid_until: new Date(now.getTime() + 8 * 3600_000).toISOString(), released_at: null,
    });
    setMessage("APR salva localmente e enfileirada para sincronização.");
  };
  return <ScrollView style={styles.root} contentContainerStyle={styles.content}><Text style={styles.title}>Liberação diária da frente</Text><Text style={styles.subtitle}>EPI/EPC obrigatório · NR-10 e NR-35</Text>
    <TextInput style={styles.input} placeholder="Observação da atividade" placeholderTextColor="#7b8794" value={observation} onChangeText={setObservation} multiline />
    <View style={styles.row}><TextInput style={[styles.input, styles.half]} placeholder="Tensão (kV)" placeholderTextColor="#7b8794" keyboardType="decimal-pad" value={voltage} onChangeText={setVoltage} /><TextInput style={[styles.input, styles.half]} placeholder="Altura (m)" placeholderTextColor="#7b8794" keyboardType="decimal-pad" value={height} onChangeText={setHeight} /></View>
    <Text style={styles.section}>Checklist {required.length ? `(${required.length} itens)` : "(sem regra adicional)"}</Text>{required.map(key => <Pressable key={key} style={styles.check} onPress={() => setChecked(value => ({ ...value, [key]: !value[key] }))}><Text style={styles.checkMark}>{checked[key] ? "☑" : "☐"}</Text><Text style={styles.checkText}>{key.replaceAll("_", " ").toUpperCase()}</Text></Pressable>)}
    <Text style={styles.section}>Assinatura digital do TST</Text><SignaturePad onChange={svg => void sign("TST", svg)} /><Text style={styles.signed}>{tst ? "Assinado" : "Aguardando assinatura"}</Text>
    <Text style={styles.section}>Assinatura digital do Encarregado</Text><SignaturePad onChange={svg => void sign("ENCARREGADO", svg)} /><Text style={styles.signed}>{encarregado ? "Assinado" : "Aguardando assinatura"}</Text>
    <Text style={styles.message}>{message}</Text><Pressable style={[styles.button, !complete && styles.disabled]} disabled={!complete} onPress={() => void submit()}><Text style={styles.buttonText}>SALVAR E ENFILEIRAR APR</Text></Pressable><Pressable style={styles.back} onPress={() => router.back()}><Text style={styles.backText}>VOLTAR</Text></Pressable>
  </ScrollView>;
}
const styles = StyleSheet.create({ root: { flex: 1, backgroundColor: "#07111f" }, content: { padding: 18, gap: 12 }, title: { color: "#fff", fontSize: 28, fontWeight: "900" }, subtitle: { color: "#f5c542", fontSize: 16, fontWeight: "700" }, input: { minHeight: 56, backgroundColor: "#fff", borderRadius: 8, padding: 14, fontSize: 17, color: "#111" }, row: { flexDirection: "row", gap: 10 }, half: { flex: 1 }, section: { color: "#fff", fontSize: 19, fontWeight: "900", marginTop: 12 }, check: { minHeight: 52, backgroundColor: "#15304a", borderRadius: 8, flexDirection: "row", alignItems: "center", paddingHorizontal: 14, gap: 12 }, checkMark: { fontSize: 27, color: "#f5c542" }, checkText: { color: "#fff", fontSize: 15, fontWeight: "800" }, signed: { color: "#89e08a", fontWeight: "800" }, message: { color: "#fff", fontSize: 16, lineHeight: 22 }, button: { minHeight: 58, borderRadius: 10, alignItems: "center", justifyContent: "center", backgroundColor: "#f5c542", marginTop: 10 }, disabled: { opacity: 0.4 }, buttonText: { color: "#111", fontSize: 16, fontWeight: "900" }, back: { minHeight: 48, justifyContent: "center", alignItems: "center" }, backText: { color: "#fff", fontWeight: "800" } });
