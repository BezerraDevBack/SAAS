// IP — Caramurú Construções — assinatura do autor

import { useMemo, useRef, useState } from "react";
import { PanResponder, StyleSheet, View } from "react-native";

type Point = { x: number; y: number };
export function SignaturePad({ onChange }: { onChange: (svg: string) => void }) {
  const [points, setPoints] = useState<Point[]>([]);
  const pointsRef = useRef<Point[]>([]);
  const responder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderGrant: event => { const p = { x: event.nativeEvent.locationX, y: event.nativeEvent.locationY }; pointsRef.current = [p]; setPoints([p]); },
    onPanResponderMove: event => { const p = { x: event.nativeEvent.locationX, y: event.nativeEvent.locationY }; pointsRef.current = [...pointsRef.current, p]; setPoints([...pointsRef.current]); },
    onPanResponderRelease: () => { const d = pointsRef.current.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" "); onChange(`<svg xmlns="http://www.w3.org/2000/svg" width="360" height="220"><path d="${d}" fill="none" stroke="#07111f" stroke-width="4" stroke-linecap="round"/></svg>`); },
  }), [onChange]);
  return <View style={styles.pad} {...responder.panHandlers}>{points.map((p, index) => <View key={`${index}-${p.x}-${p.y}`} style={[styles.dot, { left: p.x - 2, top: p.y - 2 }]} />)}</View>;
}
const styles = StyleSheet.create({ pad: { height: 220, width: "100%", backgroundColor: "#fff", borderWidth: 3, borderColor: "#f5c542", borderRadius: 8, overflow: "hidden" }, dot: { position: "absolute", width: 5, height: 5, borderRadius: 3, backgroundColor: "#07111f" } });
