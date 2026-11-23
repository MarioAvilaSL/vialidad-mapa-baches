// Rutas con nombre guardadas en el dispositivo (IndexedDB): se pueden usar sin conexión con el servidor.
import { guardarLocal, leerLocal } from "../plataforma/datosLocales.js";

const CLAVE = "rutas";
export const MAXIMO = 20;

export async function listarRutas() {
  const v = await leerLocal(CLAVE);
  return Array.isArray(v) ? v : [];
}

/** Guarda una ruta con nombre (la más reciente primero). Devuelve la lista nueva, o null si no se pudo guardar. */
export async function guardarRuta({ nombre, resultado, indice }) {
  const lista = await listarRutas();
  const limpio = (nombre || "").trim().slice(0, 60) || "Ruta sin nombre";
  const nueva = { id: `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`, nombre: limpio, resultado, indice, guardada: new Date().toISOString() };
  const siguiente = [nueva, ...lista].slice(0, MAXIMO);
  return (await guardarLocal(CLAVE, siguiente)) ? siguiente : null;
}

export async function borrarRuta(id) {
  const siguiente = (await listarRutas()).filter((r) => r.id !== id);
  await guardarLocal(CLAVE, siguiente);
  return siguiente;
}
