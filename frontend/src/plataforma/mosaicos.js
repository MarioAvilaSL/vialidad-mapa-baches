// Mapa guardado en el teléfono. En la app Android, cada mosaico (cuadradito) del mapa que se ve con conexión se guarda
// en IndexedDB; sin conexión se reutiliza. Solo se guarda lo que la persona ya miró: OpenStreetMap no permite descargar
// zonas enteras de golpe. Hay un límite de espacio; al pasarlo se borran primero los mosaicos más antiguos.
// En el navegador de la PC no se usa (el navegador ya tiene su propia caché) y la capa es la normal de Leaflet.
import L from "leaflet";
import { esNativo } from "./servidor.js";

const BD = "vialidad-mapa-mosaicos", ALMACEN = "mosaicos", CLAVE_LIMITE = "vialidad-mapa.mosaicos.limite_mb";
export const LIMITES_MB = [0, 50, 100, 200, 500];     // 0 = no guardar

export function limiteMosaicosMb() {
  try {
    const v = Number(localStorage.getItem(CLAVE_LIMITE));
    return localStorage.getItem(CLAVE_LIMITE) !== null && LIMITES_MB.includes(v) ? v : 100;
  } catch { return 100; }
}
export function fijarLimiteMosaicosMb(mb) {
  try { localStorage.setItem(CLAVE_LIMITE, String(mb)); } catch { /* se usa el valor por defecto */ }
}

let abierta = null;
function abrir() {
  if (!abierta) {
    abierta = new Promise((ok, mal) => {
      if (typeof indexedDB === "undefined") return mal(new Error("sin IndexedDB"));
      const q = indexedDB.open(BD, 1);
      q.onupgradeneeded = () => q.result.createObjectStore(ALMACEN);
      q.onsuccess = () => ok(q.result);
      q.onerror = () => mal(q.error);
    });
    abierta.catch(() => { abierta = null; });
  }
  return abierta;
}
const pedir = (r) => new Promise((ok, mal) => { r.onsuccess = () => ok(r.result); r.onerror = () => mal(r.error); });

async function leer(clave) {
  const db = await abrir();
  return pedir(db.transaction(ALMACEN).objectStore(ALMACEN).get(clave));
}
async function escribir(clave, registro) {
  const db = await abrir();
  await new Promise((ok, mal) => {
    const t = db.transaction(ALMACEN, "readwrite");
    t.objectStore(ALMACEN).put(registro, clave);
    t.oncomplete = ok; t.onerror = () => mal(t.error);
  });
}

/** Cuántos mosaicos hay guardados y cuánto ocupan. */
export async function estadoMosaicos() {
  try {
    const db = await abrir();
    return await new Promise((ok, mal) => {
      let n = 0, bytes = 0;
      const q = db.transaction(ALMACEN).objectStore(ALMACEN).openCursor();
      q.onsuccess = () => {
        const c = q.result;
        if (c) { n++; bytes += c.value.bytes || 0; c.continue(); } else ok({ n, bytes });
      };
      q.onerror = () => mal(q.error);
    });
  } catch { return { n: 0, bytes: 0 }; }
}

export async function borrarMosaicos() {
  try {
    const db = await abrir();
    await new Promise((ok) => { const t = db.transaction(ALMACEN, "readwrite"); t.objectStore(ALMACEN).clear(); t.oncomplete = ok; t.onerror = ok; });
  } catch { /* nada que borrar */ }
}

// Borra los más antiguos hasta quedar en el 90 % del límite
async function recortar() {
  const tope = limiteMosaicosMb() * 1024 * 1024;
  try {
    const db = await abrir();
    const filas = await new Promise((ok, mal) => {
      const lista = [];
      const q = db.transaction(ALMACEN).objectStore(ALMACEN).openCursor();
      q.onsuccess = () => { const c = q.result; if (c) { lista.push({ k: c.key, t: c.value.t || 0, b: c.value.bytes || 0 }); c.continue(); } else ok(lista); };
      q.onerror = () => mal(q.error);
    });
    let total = filas.reduce((s, f) => s + f.b, 0);
    if (total <= tope) return;
    filas.sort((a, b) => a.t - b.t);
    const t = db.transaction(ALMACEN, "readwrite");
    const alm = t.objectStore(ALMACEN);
    for (const f of filas) {
      if (total <= tope * 0.9) break;
      alm.delete(f.k); total -= f.b;
    }
  } catch { /* sin recorte */ }
}

let escritas = 0;
async function mosaico(clave, url) {
  if (limiteMosaicosMb() === 0) return { url };
  try {
    const r = await leer(clave);
    if (r?.blob) return { url: URL.createObjectURL(r.blob), blob: true };
  } catch { return { url }; }
  const resp = await fetch(url, { mode: "cors" });          // sin conexión lanza: el mosaico queda vacío
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const blob = await resp.blob();
  escribir(clave, { blob, bytes: blob.size, t: Date.now() })
    .then(() => { if (++escritas % 40 === 0) recortar(); })
    .catch(() => { /* sin espacio: se sigue sin guardar */ });
  return { url: URL.createObjectURL(blob), blob: true };
}

const CapaGuardada = L.TileLayer.extend({
  createTile(coords, hecho) {
    const img = document.createElement("img");
    img.alt = "";
    img.setAttribute("role", "presentation");
    const url = this.getTileUrl(coords);
    mosaico(`${coords.z}/${coords.x}/${coords.y}`, url)
      .then((m) => {
        img.onload = () => hecho(null, img);
        img.onerror = (e) => hecho(e, img);
        img.src = m.url;
      })
      .catch((e) => hecho(e, img));
    return img;
  },
  onAdd(mapa) {
    L.TileLayer.prototype.onAdd.call(this, mapa);
    this.on("tileunload", (e) => { if (e.tile?.src?.startsWith("blob:")) URL.revokeObjectURL(e.tile.src); });
  },
});

/** Capa de mosaicos: con caché en la app Android, normal en el navegador. */
export function capaMosaicos(url, opciones) {
  return esNativo() ? new CapaGuardada(url, opciones) : L.tileLayer(url, opciones);
}
