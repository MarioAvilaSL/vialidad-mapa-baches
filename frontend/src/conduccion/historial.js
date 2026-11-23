// Historial de avisos emitidos (los últimos 200), guardado en el dispositivo.
import { reactive, watch } from "vue";

const CLAVE = "vialidad-mapa.historial.v1";
const MAX = 200;

function leer() {
  try {
    const l = JSON.parse(localStorage.getItem(CLAVE) || "[]");
    return Array.isArray(l) ? l.slice(0, MAX) : [];
  } catch {
    return [];
  }
}

export const historial = reactive({ items: leer() });
watch(() => historial.items, () => {
  try { localStorage.setItem(CLAVE, JSON.stringify(historial.items)); } catch { /* en memoria */ }
}, { deep: true });

export function registrar(aviso, texto, simulado) {
  historial.items.unshift({
    t: Date.now(), tipo: aviso.tipo, sev: aviso.sev, n: aviso.n, distancia: Math.round(aviso.distancia), texto,
    tramo: aviso.tramo ?? null, ciudad: aviso.ciudad ?? null, lat: aviso.lat, lon: aviso.lon, simulado: !!simulado,
  });
  if (historial.items.length > MAX) historial.items.length = MAX;
}
export const borrarHistorial = () => { historial.items = []; };
