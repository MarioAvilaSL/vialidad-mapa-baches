// Presentación de la severidad: color Y tamaño (el color solo no basta para quien no distingue colores).
export const SEV = {
  alta: { color: "#d62828", radio: 9, etiqueta: "Alta" },
  media: { color: "#f08c00", radio: 7, etiqueta: "Media" },
  baja: { color: "#2f9e44", radio: 5, etiqueta: "Baja" },
};
export const ORDEN_SEV = ["alta", "media", "baja"];

// Los textos del mapa vienen de la base de datos: se escapan antes de meterlos en HTML (popups de Leaflet).
export const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export function fechaLocal(iso, tz) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("es-EC", { timeZone: tz || "America/Guayaquil", dateStyle: "medium", timeStyle: "short" });
  } catch {
    return new Date(iso).toLocaleString("es-EC");
  }
}

const PUNTOS = ["norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste"];
export const rumboTexto = (deg) => (deg == null ? null : `hacia el ${PUNTOS[Math.round(deg / 45) % 8]} (${Math.round(deg)}°)`);
