// Ajustes de alertas y conducción. Se guardan en el navegador del dispositivo (localStorage), porque el motor de
// alertas corre en el dispositivo. En la Fase 6 se podrán gestionar también desde la sección de configuración.
import { reactive, watch } from "vue";

export const DEFECTO = {
  radio_m: 150,
  nivel_min: "media",
  zonas: true,
  voz: true,
  sonido: true,
  vibracion: true,
  mapa: true,
};
const RANGOS = { radio_m: [50, 500] };
const CLAVE = "vialidad-mapa.ajustes.v1";

function leer() {
  try {
    const crudo = JSON.parse(localStorage.getItem(CLAVE) || "{}");
    const a = {};
    for (const k of Object.keys(DEFECTO)) {
      const v = crudo[k];
      if (typeof DEFECTO[k] === "boolean") a[k] = typeof v === "boolean" ? v : DEFECTO[k];
      else if (k === "nivel_min") a[k] = ["baja", "media", "alta"].includes(v) ? v : DEFECTO[k];
      else a[k] = Number.isFinite(v) ? Math.min(RANGOS[k][1], Math.max(RANGOS[k][0], v)) : DEFECTO[k];
    }
    return a;
  } catch {
    return { ...DEFECTO };
  }
}

export const ajustes = reactive(leer());
watch(ajustes, () => {
  try { localStorage.setItem(CLAVE, JSON.stringify(ajustes)); } catch { /* sin almacenamiento: se usan en memoria */ }
}, { deep: true });
