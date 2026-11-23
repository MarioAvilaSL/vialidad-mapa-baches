// GPS del dispositivo. Devuelve lecturas con el mismo formato en el navegador y en la app:
//   {lat, lon, t (ms), velocidad (m/s | null), rumbo (° | null), precision (m | null)}
//  · Navegador: navigator.geolocation (solo con https o en localhost).
//  · App Android: plugin de ubicación en segundo plano con un servicio en primer plano (aviso fijo en la barra de
//    notificaciones), de modo que sigue recibiendo ubicación con la pantalla apagada o con otra app delante.
import { esNativo } from "./servidor.js";

const lecturaWeb = (p) => ({ lat: p.coords.latitude, lon: p.coords.longitude, t: p.timestamp, velocidad: p.coords.speed,
  rumbo: p.coords.heading, precision: p.coords.accuracy });

/**
 * Empieza a seguir la ubicación.
 * @returns {Promise<() => void>} función para detener el seguimiento
 * @throws Error con `.mensaje` legible para el usuario
 */
export async function iniciarGps(alLeer, alFallar) {
  if (esNativo()) return iniciarNativo(alLeer, alFallar);

  if (!("geolocation" in navigator) || !window.isSecureContext) {
    throw new Error("El GPS del navegador solo funciona con https o en localhost. Usa la app Android para el celular.");
  }
  const id = navigator.geolocation.watchPosition(
    (p) => alLeer(lecturaWeb(p)),
    (e) => alFallar(e.code === 1 ? "Permiso de ubicación denegado. Permítelo en el navegador y vuelve a iniciar." : `No se pudo obtener la ubicación (${e.message}).`),
    { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 },
  );
  return () => navigator.geolocation.clearWatch(id);
}

async function iniciarNativo(alLeer, alFallar) {
  const { BackgroundGeolocation } = await import("@capgo/background-geolocation");
  let parar = null;
  await BackgroundGeolocation.start(
    {
      backgroundTitle: "Vialidad Mapa · conducción",
      backgroundMessage: "Avisando de baches en tu ruta",
      requestPermissions: true,
      stale: false,
      distanceFilter: 0,
    },
    (loc, error) => {
      if (error) {
        if (error.code === "NOT_AUTHORIZED") {
          alFallar("Falta el permiso de ubicación. Pulsa «Abrir ajustes» y permite la ubicación para Vialidad Mapa.", "permiso");
        } else {
          alFallar(`No se pudo obtener la ubicación (${error.message || error.code}).`);
        }
        return;
      }
      if (!loc) return;
      alLeer({
        lat: loc.latitude, lon: loc.longitude,
        t: loc.time ?? Date.now(),
        velocidad: loc.speed != null && loc.speed >= 0 ? loc.speed : null,
        rumbo: loc.bearing != null && loc.bearing >= 0 ? loc.bearing : null,
        precision: loc.accuracy ?? null,
      });
    },
  );
  parar = async () => { try { await BackgroundGeolocation.stop(); } catch { /* ya detenido */ } };
  return () => { parar(); };
}

/** Abre los ajustes de la app para dar el permiso de ubicación (solo en la app). */
export async function abrirAjustesUbicacion() {
  if (!esNativo()) return;
  try {
    const { BackgroundGeolocation } = await import("@capgo/background-geolocation");
    await BackgroundGeolocation.openSettings();
  } catch { /* nada */ }
}
