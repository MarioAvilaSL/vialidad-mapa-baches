// Ajustes compartidos guardados en el servidor (zonas críticas y ancho del corredor de las rutas).
// A diferencia de los ajustes de alertas (voz, tono…), que son de cada dispositivo, estos son los mismos en la web y en Android.
import { reactive } from "vue";
import { api } from "./api.js";

const FABRICA = { eps_m: 30, min_vecinos: 6, min_baches: 8, ancho_m: 30 };

export const servidor = reactive({ valores: { ...FABRICA }, defectos: { ...FABRICA }, actualizado_en: null, cargado: false, error: "" });

function aplicar(r) {
  servidor.valores = { ...r.valores };
  servidor.defectos = { ...r.defectos };
  servidor.actualizado_en = r.actualizado_en;
  servidor.cargado = true;
  servidor.error = "";
}

let pendiente = null;

/** Carga los ajustes (una vez; `forzar` vuelve a pedirlos). Si el servidor no responde, se usan los de fábrica. */
export function cargarAjustesServidor(forzar = false) {
  if (!pendiente || forzar) {
    pendiente = api("/ajustes").then(aplicar).catch((e) => {
      servidor.error = e.detalle || e.message;
      pendiente = null;                 // se reintenta la próxima vez
    });
  }
  return pendiente;
}

export async function guardarAjustesServidor(valores) {
  aplicar(await api("/ajustes", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(valores) }));
}

export async function restablecerAjustesServidor() {
  aplicar(await api("/ajustes", { method: "DELETE" }));
}
