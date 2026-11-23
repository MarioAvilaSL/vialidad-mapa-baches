// Copia local (IndexedDB) de los datos que necesita el modo de conducción: así funciona aunque el servidor no sea
// alcanzable (por ejemplo, con datos móviles lejos de la red de la PC). Si IndexedDB no está disponible, no se guarda nada.
const BD = "vialidad-mapa", ALMACEN = "datos";

function abrir() {
  return new Promise((resolver, rechazar) => {
    if (typeof indexedDB === "undefined") return rechazar(new Error("sin IndexedDB"));
    const q = indexedDB.open(BD, 1);
    q.onupgradeneeded = () => q.result.createObjectStore(ALMACEN);
    q.onsuccess = () => resolver(q.result);
    q.onerror = () => rechazar(q.error);
  });
}

export async function guardarLocal(clave, valor) {
  try {
    const db = await abrir();
    await new Promise((ok, mal) => {
      const t = db.transaction(ALMACEN, "readwrite");
      t.objectStore(ALMACEN).put(valor, clave);
      t.oncomplete = ok;
      t.onerror = () => mal(t.error);
    });
    db.close();
    return true;
  } catch {
    return false;
  }
}

export async function leerLocal(clave) {
  try {
    const db = await abrir();
    const v = await new Promise((ok, mal) => {
      const q = db.transaction(ALMACEN).objectStore(ALMACEN).get(clave);
      q.onsuccess = () => ok(q.result ?? null);
      q.onerror = () => mal(q.error);
    });
    db.close();
    return v;
  } catch {
    return null;
  }
}

export async function borrarLocal(clave) {
  try {
    const db = await abrir();
    await new Promise((ok) => { const t = db.transaction(ALMACEN, "readwrite"); t.objectStore(ALMACEN).delete(clave); t.oncomplete = ok; t.onerror = ok; });
    db.close();
  } catch { /* nada */ }
}
