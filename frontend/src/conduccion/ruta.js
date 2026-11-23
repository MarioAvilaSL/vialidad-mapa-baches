// Seguimiento de una ruta planificada: dónde va el vehículo sobre ella y qué tan lejos queda el destino.
// JavaScript puro (se prueba con `npm test`).
import { distancia } from "./motor.js";

const RAD = Math.PI / 180;
const R = 6371000;

export class Recorrido {
  /** @param {number[][]} coords  [[lon, lat], …] de la ruta (como la entrega el servidor) */
  constructor(coords) {
    this.p = coords;
    this.acum = [0];
    for (let i = 1; i < coords.length; i++) {
      this.acum.push(this.acum[i - 1] + distancia(coords[i - 1][1], coords[i - 1][0], coords[i][1], coords[i][0]));
    }
    this.total = this.acum[this.acum.length - 1];
    this.ultimo = 0;
  }

  _mejor(lat, lon, desde, hasta) {
    const kx = Math.cos(lat * RAD) * RAD * R, ky = RAD * R;
    let mejor = { d: Infinity, i: 0, t: 0 };
    for (let i = Math.max(0, desde); i < Math.min(this.p.length - 1, hasta); i++) {
      const ax = (this.p[i][0] - lon) * kx, ay = (this.p[i][1] - lat) * ky;
      const bx = (this.p[i + 1][0] - lon) * kx, by = (this.p[i + 1][1] - lat) * ky;
      const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy;
      const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, (-ax * dx - ay * dy) / l2));
      const d = Math.hypot(ax + t * dx, ay + t * dy);
      if (d < mejor.d) mejor = { d, i, t };
    }
    return mejor;
  }

  /** Posición sobre la ruta: lateral_m (distancia a la ruta), avance_m (recorrido) y restante_m. */
  proyectar(lat, lon) {
    // Primero se busca cerca de donde se estaba (evita saltar a otro tramo si la ruta pasa dos veces por el mismo sitio)
    let m = this._mejor(lat, lon, this.ultimo - 10, this.ultimo + 300);
    if (m.d > 50) m = this._mejor(lat, lon, 0, this.p.length);
    this.ultimo = m.i;
    const tramo = this.acum[m.i + 1] - this.acum[m.i];
    const avance = this.acum[m.i] + m.t * tramo;
    return { lateral_m: m.d, avance_m: avance, restante_m: Math.max(0, this.total - avance) };
  }
}

/** Baches y zonas de una ruta (respuesta de /api/rutas/planificar) en el formato que espera el motor de alertas. */
export function datosDeRuta(ruta) {
  return {
    baches: {
      features: ruta.baches.map((b) => ({
        type: "Feature", geometry: { type: "Point", coordinates: [b.lon, b.lat] }, properties: { id: b.id, severidad: b.severidad },
      })),
    },
    zonas: {
      features: ruta.zonas.map((z) => ({
        type: "Feature", geometry: z.geometry,
        properties: { n: z.n, alta: z.alta, media: z.media, baja: z.baja, tramo: z.tramo, ciudad: z.ciudad, lat: z.lat, lon: z.lon },
      })),
    },
  };
}

export function textoDistancia(m) {
  if (m == null) return "";
  return m >= 1000 ? `${(m / 1000).toLocaleString("es-EC", { maximumFractionDigits: 1 })} km` : `${Math.round(m / 10) * 10} m`;
}

export function textoTiempo(s) {
  const min = Math.max(1, Math.round(s / 60));
  return min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")} min`;
}
