// Cliente mínimo de la API. En el navegador de la PC, Vite redirige /api al backend (ver vite.config.js); en la app
// Android se usa la dirección del servidor guardada en Ajustes → Conexión (ver plataforma/servidor.js).
import { baseApi, claveServidor } from "./plataforma/servidor.js";

export async function api(ruta, opciones = {}) {
  const headers = { ...(opciones.headers || {}) };
  const clave = claveServidor();
  if (clave) headers["X-Clave"] = clave;
  let r;
  try {
    r = await fetch(`${baseApi()}/api${ruta}`, { ...opciones, headers });
  } catch (e) {
    // Sin red o servidor apagado: el navegador solo dice «Failed to fetch»; se explica mejor
    throw Object.assign(new Error("No se pudo conectar con el servidor"), { status: 0, sinConexion: true, detalle: "No se pudo conectar con el servidor." });
  }
  if (!r.ok) {
    let detalle = r.statusText;
    try {
      const d = (await r.json()).detail;
      if (typeof d === "string") detalle = d;
      else if (Array.isArray(d)) detalle = d.map((x) => x.msg || JSON.stringify(x)).join("; ");   // errores de validación
    } catch { /* sin cuerpo JSON */ }
    // `detalle` es el texto para mostrar al usuario; el mensaje incluye además el código HTTP
    throw Object.assign(new Error(`${r.status}: ${detalle}`), { status: r.status, detalle });
  }
  return r.json();
}
