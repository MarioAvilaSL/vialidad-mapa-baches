// Motor de alertas del modo de conducción. Es JavaScript puro (sin Vue ni navegador): recibe posiciones GPS y devuelve
// avisos. Corre en el dispositivo, así que no depende del servidor mientras se conduce, y se puede probar con `npm test`.
//
// Reglas:
//  · Solo se avisa de lo que está ADELANTE (dentro de ±adelante_grados del sentido de marcha) y a menos del radio.
//  · Cada bache o zona se avisa UNA vez; se vuelve a armar cuando el conductor se aleja más del doble del radio.
//  · Los baches que están dentro de una zona crítica ya avisada no generan avisos propios (evita ruido).
//  · Varios baches adelante a la vez se avisan juntos, en un solo mensaje.
//  · Detenido (velocidad baja) no se avisa: evita repeticiones en un semáforo.
//  · El GPS no distingue carriles: el aviso es por zona de la vía, no por carril.

const R_TIERRA = 6371000;
const RAD = Math.PI / 180;
const VENTANA_GRUPO = 60;     // m: baches a menos de esto detrás del primero se avisan en el mismo mensaje
const RANGO = { baja: 0, media: 1, alta: 2 };

export const AJUSTES_MOTOR = {
  radio_m: 150,            // distancia mínima de aviso de un bache
  nivel_min: "media",      // severidad mínima que se avisa: baja | media | alta
  zonas: true,             // avisar zonas críticas
  adelante_grados: 60,     // semiángulo del «adelante»
  seg_anticipacion: 6,     // a más velocidad, el aviso se adelanta: radio = max(radio_m, velocidad · segundos)
  vel_min_ms: 1.5,         // por debajo de esta velocidad (m/s) se considera detenido
  precision_max_m: 50,     // se ignoran lecturas GPS peores que esto
};

// ── geometría ───────────────────────────────────────────────────────────────
export function distancia(lat1, lon1, lat2, lon2) {
  const x = (lon2 - lon1) * RAD * Math.cos(((lat1 + lat2) / 2) * RAD);
  const y = (lat2 - lat1) * RAD;
  return Math.hypot(x, y) * R_TIERRA;
}

/** Rumbo en grados (0 = norte, 90 = este) del punto 1 al punto 2. */
export function rumbo(lat1, lon1, lat2, lon2) {
  const dx = (lon2 - lon1) * Math.cos(((lat1 + lat2) / 2) * RAD);
  const dy = lat2 - lat1;
  return (Math.atan2(dx, dy) / RAD + 360) % 360;
}

export function difAngulo(a, b) {
  const d = Math.abs(a - b) % 360;
  return d > 180 ? 360 - d : d;
}

/** Punto desplazado `m` metros en el rumbo `grados`. */
export function destino(lat, lon, grados, m) {
  const d = m / R_TIERRA, b = grados * RAD;
  return [lat + (Math.cos(b) * d) / RAD, lon + (Math.sin(b) * d) / (RAD * Math.cos(lat * RAD))];
}

// Plano local en metros con origen en (lat0, lon0): suficiente a escala de ciudad.
function aPlano(lat0, lon0, lat, lon) {
  return [(lon - lon0) * RAD * Math.cos(lat0 * RAD) * R_TIERRA, (lat - lat0) * RAD * R_TIERRA];
}
function dePlano(lat0, lon0, x, y) {
  return [lat0 + y / (R_TIERRA * RAD), lon0 + x / (R_TIERRA * RAD * Math.cos(lat0 * RAD))];
}

/** Distancia (m) de un punto a un polígono GeoJSON ([[lon, lat], …]) y el punto más cercano. 0 si está dentro. */
export function distanciaAPoligono(lat, lon, anillo) {
  const p = anillo.map(([lo, la]) => aPlano(lat, lon, la, lo));      // el punto queda en el origen
  let dentro = false;
  for (let i = 0, j = p.length - 1; i < p.length; j = i++) {
    const [xi, yi] = p[i], [xj, yj] = p[j];
    if ((yi > 0) !== (yj > 0) && 0 < ((xj - xi) * (0 - yi)) / (yj - yi) + xi) dentro = !dentro;
  }
  if (dentro) return { d: 0, lat, lon, dentro: true };
  let mejor = Infinity, mx = 0, my = 0;
  for (let i = 0, j = p.length - 1; i < p.length; j = i++) {
    const [ax, ay] = p[j], [bx, by] = p[i];
    const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy;
    const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, (-ax * dx - ay * dy) / l2));
    const qx = ax + t * dx, qy = ay + t * dy, d = Math.hypot(qx, qy);
    if (d < mejor) { mejor = d; mx = qx; my = qy; }
  }
  const [qla, qlo] = dePlano(lat, lon, mx, my);
  return { d: mejor, lat: qla, lon: qlo, dentro: false };
}

function anillosDe(geom) {
  if (!geom) return [];
  if (geom.type === "Polygon") return [geom.coordinates[0]];
  if (geom.type === "MultiPolygon") return geom.coordinates.map((c) => c[0]);
  return [];
}

// ── textos ──────────────────────────────────────────────────────────────────
const redondear = (m) => (m < 25 ? Math.max(10, Math.round(m / 5) * 5) : Math.round(m / 10) * 10);
const ETIQ = { alta: "alta", media: "media", baja: "baja" };

export function textoAviso(a) {
  if (a.tipo === "llegada") return "Has llegado a tu destino.";
  if (a.tipo === "zona") {
    return a.dentro
      ? `Zona crítica. ${a.n} baches registrados. Conduce con precaución.`
      : `Zona crítica a ${redondear(a.distancia)} metros, con ${a.n} baches.`;
  }
  if (a.n === 1) return `Bache de severidad ${ETIQ[a.sev]} a ${redondear(a.distancia)} metros.`;
  return `${a.n} baches adelante, el primero a ${redondear(a.distancia)} metros.`;
}

// ── motor ───────────────────────────────────────────────────────────────────
export class Motor {
  /**
   * @param {{features: object[]}} baches  GeoJSON de /api/baches (propiedades: id, severidad)
   * @param {{features: object[]}|null} zonas  GeoJSON de /api/zonas
   */
  constructor(baches, zonas, ajustes = {}) {
    this.cfg = { ...AJUSTES_MOTOR, ...ajustes };
    this.baches = (baches?.features ?? []).map((f) => ({
      id: f.properties.id, sev: f.properties.severidad || "baja",
      lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0], zona: null,
    }));
    this.zonas = (zonas?.features ?? []).map((f, i) => {
      const anillos = anillosDe(f.geometry);
      const pts = anillos.flat();
      const lons = pts.map((q) => q[0]), lats = pts.map((q) => q[1]);
      const p = f.properties;
      return {
        i, n: p.n, alta: p.alta, media: p.media, baja: p.baja, tramo: p.tramo, ciudad: p.ciudad, lat: p.lat, lon: p.lon,
        anillos, caja: [Math.min(...lats), Math.min(...lons), Math.max(...lats), Math.max(...lons)],
      };
    });
    for (const b of this.baches) {            // a qué zona pertenece cada bache (si alguna)
      for (const z of this.zonas) {
        const [a, o, A, O] = z.caja;
        if (b.lat < a || b.lat > A || b.lon < o || b.lon > O) continue;
        if (z.anillos.some((an) => distanciaAPoligono(b.lat, b.lon, an).dentro)) { b.zona = z.i; break; }
      }
    }
    this.reiniciar();
  }

  setAjustes(a) { this.cfg = { ...this.cfg, ...a }; }

  reiniciar() {
    this.avisados = new Set();        // ids de baches ya avisados
    this.zonasAvisadas = new Set();
    this.anclaje = null;              // último punto desde el que se calculó el rumbo
    this.rumbo = null;
    this.ultima = null;
  }

  /**
   * Procesa una lectura GPS.
   * @param {{lat:number, lon:number, t:number, velocidad?:number|null, rumbo?:number|null, precision?:number|null}} pos
   * @returns {{avisos: object[], estado: object}}
   */
  actualizar(pos) {
    const c = this.cfg;
    const vacio = (extra) => ({ avisos: [], estado: { velocidad: null, rumbo: this.rumbo, parado: false, debil: false, zona: null, proximo: null, ...extra } });
    if (pos.precision != null && pos.precision > c.precision_max_m) return vacio({ debil: true });

    // velocidad: la del GPS o, si no hay, la calculada con la lectura anterior
    let v = pos.velocidad;
    if (v == null || Number.isNaN(v)) {
      v = this.ultima && pos.t > this.ultima.t
        ? distancia(this.ultima.lat, this.ultima.lon, pos.lat, pos.lon) / ((pos.t - this.ultima.t) / 1000) : 0;
    }
    this.ultima = pos;

    // sentido de marcha: el del GPS si viene y se va rápido; si no, el del desplazamiento
    if (pos.rumbo != null && !Number.isNaN(pos.rumbo) && v >= c.vel_min_ms) {
      this.rumbo = pos.rumbo;
      this.anclaje = pos;
    } else if (!this.anclaje) {
      this.anclaje = pos;
    } else if (distancia(this.anclaje.lat, this.anclaje.lon, pos.lat, pos.lon) >= 8) {
      this.rumbo = rumbo(this.anclaje.lat, this.anclaje.lon, pos.lat, pos.lon);
      this.anclaje = pos;
    }
    const parado = v < c.vel_min_ms;
    const radio = Math.min(600, Math.max(c.radio_m, v * c.seg_anticipacion));
    const radioZona = Math.min(900, Math.max(2 * c.radio_m, v * 2 * c.seg_anticipacion));
    const h = this.rumbo;
    const estado = { velocidad: v, rumbo: h, parado, debil: false, zona: null, proximo: null };

    // ── zonas ──
    const avisos = [];
    for (const z of this.zonas) {
      const [a, o, A, O] = z.caja, m = (radioZona / R_TIERRA) / RAD;
      if (pos.lat < a - m || pos.lat > A + m || pos.lon < o - 3 * m || pos.lon > O + 3 * m) {
        this.zonasAvisadas.delete(z.i);                        // lejos: se rearma
        continue;
      }
      let cerca = { d: Infinity };
      for (const an of z.anillos) { const r = distanciaAPoligono(pos.lat, pos.lon, an); if (r.d < cerca.d) cerca = r; }
      if (cerca.dentro) estado.zona = { n: z.n, tramo: z.tramo, ciudad: z.ciudad, alta: z.alta, media: z.media, baja: z.baja };
      if (cerca.d > 2 * radioZona) { this.zonasAvisadas.delete(z.i); continue; }
      if (!c.zonas || parado || this.zonasAvisadas.has(z.i) || cerca.d > radioZona) continue;
      const adelante = cerca.dentro || h == null || difAngulo(h, rumbo(pos.lat, pos.lon, cerca.lat, cerca.lon)) <= 80;
      if (!adelante) continue;
      this.zonasAvisadas.add(z.i);
      avisos.push({ tipo: "zona", n: z.n, alta: z.alta, sev: z.alta ? "alta" : z.media ? "media" : "baja", distancia: cerca.d, dentro: cerca.dentro,
        tramo: z.tramo, ciudad: z.ciudad, lat: z.lat, lon: z.lon, t: pos.t });
    }

    // ── baches ──
    const minimo = RANGO[c.nivel_min] ?? 1;
    const delante = [];
    for (const b of this.baches) {
      const d = distancia(pos.lat, pos.lon, b.lat, b.lon);
      if (d > 2 * radio) { this.avisados.delete(b.id); continue; }       // lejos: se rearma
      if (d > 30 && h != null && this.avisados.has(b.id) && difAngulo(h, rumbo(pos.lat, pos.lon, b.lat, b.lon)) > 120) {
        this.avisados.delete(b.id);                                      // ya lo pasamos: si damos la vuelta, se avisa otra vez
        continue;
      }
      if (RANGO[b.sev] < minimo || d > radio + VENTANA_GRUPO) continue;
      if (d > 15 && (h == null || difAngulo(h, rumbo(pos.lat, pos.lon, b.lat, b.lon)) > c.adelante_grados)) continue;
      delante.push({ ...b, d });
    }
    delante.sort((p, q) => p.d - q.d);
    if (delante.length && delante[0].d <= radio) estado.proximo = { tipo: "bache", distancia: delante[0].d, sev: delante[0].sev, n: delante.length };
    if (estado.zona === null) {
      const z = avisos.find((x) => x.tipo === "zona");
      if (z && !z.dentro) estado.proximo = { tipo: "zona", distancia: z.distancia, sev: z.sev, n: z.n };
    }

    if (!parado) {
      let nuevos = delante.filter((b) => !this.avisados.has(b.id)
        && !(c.zonas && b.zona != null && (this.zonasAvisadas.has(b.zona))));
      // se avisa cuando el más cercano entra al radio, y con él los que le siguen dentro de la ventana de agrupación
      if (nuevos.length && nuevos[0].d <= radio) nuevos = nuevos.filter((b) => b.d <= nuevos[0].d + VENTANA_GRUPO);
      else nuevos = [];
      if (nuevos.length) {
        const peor = nuevos.reduce((m, b) => (RANGO[b.sev] > RANGO[m] ? b.sev : m), "baja");
        avisos.push({ tipo: "bache", n: nuevos.length, sev: peor, distancia: nuevos[0].d, ids: nuevos.map((b) => b.id),
          lat: nuevos[0].lat, lon: nuevos[0].lon, t: pos.t });
        nuevos.forEach((b) => this.avisados.add(b.id));
      }
    }
    avisos.sort((p, q) => (p.tipo === "zona" ? -1 : 1) - (q.tipo === "zona" ? -1 : 1));
    return { avisos, estado };
  }
}

// ── simulación (para probar sin salir a conducir) ───────────────────────────
/** Ruta recta que atraviesa la zona: entra 500 m antes del primer bache y sale 200 m después del último. */
export function rutaPorZona(motor, indiceZona, antes = 500, despues = 200) {
  const pts = motor.baches.filter((b) => b.zona === indiceZona);
  if (pts.length < 2) return null;
  let A = pts[0], B = pts[1], mejor = -1;
  for (const p of pts) for (const q of pts) {
    const d = distancia(p.lat, p.lon, q.lat, q.lon);
    if (d > mejor) { mejor = d; A = p; B = q; }
  }
  const h = rumbo(A.lat, A.lon, B.lat, B.lon);
  return [destino(A.lat, A.lon, h, -antes), destino(B.lat, B.lon, h, despues)];
}

/** Lecturas GPS simuladas a lo largo de una ruta ([[lat, lon], …]), una por `dt` segundos, a velocidad constante. */
export function* lecturasSimuladas(ruta, velocidadKmh = 40, dt = 1, t0 = 0) {
  const v = velocidadKmh / 3.6, paso = v * dt;
  const tramos = [];
  let total = 0;
  for (let i = 0; i + 1 < ruta.length; i++) {
    const [la1, lo1] = ruta[i], [la2, lo2] = ruta[i + 1];
    const l = distancia(la1, lo1, la2, lo2);
    if (l > 0) { tramos.push({ la1, lo1, la2, lo2, l, ini: total, h: rumbo(la1, lo1, la2, lo2) }); total += l; }
  }
  if (!tramos.length) return;
  let k = 0, t = t0;
  for (let s = 0; s <= total; s += paso) {
    while (k < tramos.length - 1 && s > tramos[k].ini + tramos[k].l) k++;
    const g = tramos[k], f = Math.min(1, (s - g.ini) / g.l);
    yield { lat: g.la1 + (g.la2 - g.la1) * f, lon: g.lo1 + (g.lo2 - g.lo1) * f, t, velocidad: v, rumbo: g.h, precision: 5 };
    t += dt * 1000;
  }
}
