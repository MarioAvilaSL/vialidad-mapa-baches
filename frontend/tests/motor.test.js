import test from "node:test";
import assert from "node:assert/strict";
import { Motor, destino, distanciaAPoligono, lecturasSimuladas, rutaPorZona, textoAviso, difAngulo } from "../src/conduccion/motor.js";

const LAT = -3.265, LON = -79.955;
const bache = (id, lat, lon, severidad = "alta") => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: { id, severidad } });
const coleccion = (...f) => ({ type: "FeatureCollection", features: f });
// punto a `m` metros al norte (rumbo 0) del origen
const norte = (m) => destino(LAT, LON, 0, m);
const correr = (motor, ruta, kmh = 40) => {
  const avisos = [];
  for (const p of lecturasSimuladas(ruta, kmh)) { const r = motor.actualizar(p); r.avisos.forEach((a) => avisos.push({ ...a, en: p })); }
  return avisos;
};

test("avisa de un bache adelante una sola vez, dentro del radio", () => {
  const [bl, bo] = norte(300);
  const m = new Motor(coleccion(bache(1, bl, bo)), null, { radio_m: 150 });
  const a = correr(m, [[LAT, LON], norte(600)]);
  assert.equal(a.length, 1);
  assert.equal(a[0].tipo, "bache");
  assert.ok(a[0].distancia <= 170 && a[0].distancia > 100, `distancia ${a[0].distancia}`);
  assert.match(textoAviso(a[0]), /Bache de severidad alta a \d+ metros/);
});

test("no avisa de un bache que quedó atrás ni de uno lateral", () => {
  const atras = norte(-100), lado = destino(LAT, LON, 90, 60);
  const m = new Motor(coleccion(bache(1, atras[0], atras[1]), bache(2, ...[norte(300)[0], destino(LAT, LON, 90, 80)[1]])), null);
  assert.equal(correr(m, [[LAT, LON], norte(100)]).length, 0);
  assert.ok(lado);
});

test("detenido no avisa; al arrancar sí", () => {
  const [bl, bo] = norte(100);
  const m = new Motor(coleccion(bache(1, bl, bo)), null);
  for (let t = 0; t < 5; t++) assert.equal(m.actualizar({ lat: LAT, lon: LON, t: t * 1000, velocidad: 0, rumbo: 0, precision: 5 }).avisos.length, 0);
  const r = m.actualizar({ lat: LAT, lon: LON, t: 6000, velocidad: 8, rumbo: 0, precision: 5 });
  assert.equal(r.avisos.length, 1);
});

test("respeta el nivel mínimo de severidad", () => {
  const [bl, bo] = norte(200);
  const baja = coleccion(bache(1, bl, bo, "baja"));
  assert.equal(correr(new Motor(baja, null, { nivel_min: "media" }), [[LAT, LON], norte(400)]).length, 0);
  assert.equal(correr(new Motor(baja, null, { nivel_min: "baja" }), [[LAT, LON], norte(400)]).length, 1);
});

test("agrupa varios baches cercanos en un solo aviso", () => {
  const m = new Motor(coleccion(bache(1, ...norte(300)), bache(2, ...norte(320)), bache(3, ...norte(340), "media")), null);
  const a = correr(m, [[LAT, LON], norte(500)]);
  assert.equal(a.length, 1);
  assert.equal(a[0].n, 3);
  assert.match(textoAviso(a[0]), /3 baches adelante/);
});

test("se vuelve a armar al alejarse y regresar", () => {
  const m = new Motor(coleccion(bache(1, ...norte(300))), null);
  const ida = correr(m, [[LAT, LON], norte(500)]);
  const vuelta = correr(m, [norte(500), [LAT, LON]]);     // de regreso el bache queda adelante otra vez
  assert.equal(ida.length, 1);
  assert.equal(vuelta.length, 1);
});

test("calcula el rumbo desde el desplazamiento si el GPS no lo informa", () => {
  const m = new Motor(coleccion(bache(1, ...norte(120))), null);
  let avisos = 0;
  for (let i = 0; i < 6; i++) {
    const [la, lo] = norte(i * 10);
    avisos += m.actualizar({ lat: la, lon: lo, t: i * 1000, velocidad: null, rumbo: null, precision: 8 }).avisos.length;
  }
  assert.equal(avisos, 1);
  assert.ok(difAngulo(m.rumbo, 0) < 5);
});

test("ignora lecturas con mala precisión", () => {
  const m = new Motor(coleccion(bache(1, ...norte(100))), null);
  const r = m.actualizar({ lat: LAT, lon: LON, t: 0, velocidad: 10, rumbo: 0, precision: 200 });
  assert.equal(r.avisos.length, 0);
  assert.equal(r.estado.debil, true);
});

// zona: cuadrado de ~100 m de lado entre 400 y 500 m al norte; baches dentro
function zonaDePrueba() {
  const [a, o] = norte(400), [A] = norte(500), [, O] = destino(LAT, LON, 90, 50), [, o2] = destino(LAT, LON, 270, 50);
  const anillo = [[o2, a], [O, a], [O, A], [o2, A], [o2, a]];
  const zona = { type: "Feature", geometry: { type: "Polygon", coordinates: [anillo] },
    properties: { n: 12, alta: 4, media: 5, baja: 3, tramo: "Av. Bolívar", ciudad: "Pasaje", lat: norte(450)[0], lon: LON } };
  return { zonas: coleccion(zona), baches: coleccion(bache(1, ...norte(420)), bache(2, ...norte(450), "media"), bache(3, ...norte(480))) };
}

test("avisa la zona crítica al acercarse y no avisa de sus baches uno por uno", () => {
  const { zonas, baches } = zonaDePrueba();
  const m = new Motor(baches, zonas, { radio_m: 150 });
  const a = correr(m, [[LAT, LON], norte(700)]);
  const z = a.filter((x) => x.tipo === "zona"), b = a.filter((x) => x.tipo === "bache");
  assert.equal(z.length, 1);
  assert.equal(z[0].n, 12);
  assert.equal(b.length, 0);
  assert.match(textoAviso(z[0]), /Zona crítica a \d+ metros, con 12 baches/);
});

test("dentro de la zona el estado lo indica", () => {
  const { zonas, baches } = zonaDePrueba();
  const m = new Motor(baches, zonas);
  let dentro = false;
  for (const p of lecturasSimuladas([[LAT, LON], norte(700)], 40)) dentro ||= !!m.actualizar(p).estado.zona;
  assert.ok(dentro);
});

test("con las zonas desactivadas se avisa de los baches individuales", () => {
  const { zonas, baches } = zonaDePrueba();
  const a = correr(new Motor(baches, zonas, { zonas: false }), [[LAT, LON], norte(700)]);
  assert.equal(a.filter((x) => x.tipo === "zona").length, 0);
  assert.ok(a.filter((x) => x.tipo === "bache").length >= 1);
});

test("rutaPorZona atraviesa la zona y el simulador dispara el aviso", () => {
  const { zonas, baches } = zonaDePrueba();
  const m = new Motor(baches, zonas);
  const ruta = rutaPorZona(m, 0);
  assert.ok(ruta);
  assert.equal(correr(m, ruta).filter((x) => x.tipo === "zona").length, 1);
});

test("distanciaAPoligono: dentro = 0, fuera = distancia al borde", () => {
  const [a, o] = norte(100), [A] = norte(200), [, O] = destino(LAT, LON, 90, 50), [, o2] = destino(LAT, LON, 270, 50);
  const anillo = [[o2, a], [O, a], [O, A], [o2, A], [o2, a]];
  assert.equal(distanciaAPoligono(...norte(150), anillo).dentro, true);
  const fuera = distanciaAPoligono(LAT, LON, anillo);
  assert.ok(Math.abs(fuera.d - 100) < 1, `d=${fuera.d}`);
  assert.ok(o !== undefined);
});
