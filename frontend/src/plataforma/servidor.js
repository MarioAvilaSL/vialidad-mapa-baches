// Dónde está el servidor y con qué clave se habla con él.
//  · En el navegador (PC) la API está en el mismo sitio que la página (Vite la redirige al backend): base vacía.
//  · En la app Android la página sale del propio teléfono, así que hay que indicar la dirección del servidor
//    (por ejemplo http://192.168.1.50:8001, la IP de la PC). Se guarda en el dispositivo.
import { Capacitor } from "@capacitor/core";

export const esNativo = () => Capacitor.isNativePlatform();

const K_URL = "vialidad-mapa.servidor.url";
const K_CLAVE = "vialidad-mapa.servidor.clave";

function leer(k) { try { return localStorage.getItem(k) || ""; } catch { return ""; } }
function escribir(k, v) { try { if (v) localStorage.setItem(k, v); else localStorage.removeItem(k); } catch { /* sin almacenamiento */ } }

/** Normaliza lo que escribe el usuario: añade http:// si falta y quita la barra final. */
export function normalizarUrl(texto) {
  let t = (texto || "").trim();
  if (!t) return "";
  if (!/^https?:\/\//i.test(t)) t = "http://" + t;
  try {
    const u = new URL(t);
    return `${u.protocol}//${u.host}${u.pathname.replace(/\/+$/, "")}`;
  } catch {
    return "";
  }
}

export const urlServidor = () => leer(K_URL);
export const claveServidor = () => leer(K_CLAVE);

export function guardarServidor(url, clave) {
  escribir(K_URL, normalizarUrl(url));
  escribir(K_CLAVE, (clave || "").trim());
}

/** Base de la API: «» (relativa) en el navegador de la PC, la dirección guardada en la app. */
export const baseApi = () => (esNativo() ? urlServidor() : "");

/** URL absoluta de un recurso del servidor (p. ej. una imagen de evidencia /media/…). */
export const urlRecurso = (ruta) => (ruta && ruta.startsWith("/") ? baseApi() + ruta : ruta);

export const hayServidor = () => !esNativo() || !!urlServidor();
