import test from "node:test";
import assert from "node:assert/strict";
import { Recorrido, datosDeRuta, textoDistancia, textoTiempo } from "../src/conduccion/ruta.js";
import { Motor, destino, lecturasSimuladas, distancia } from "../src/conduccion/motor.js";

const LAT = -3.265, LON = -79.955;
const al = (rumbo, m, [la, lo] = [LAT, LON]) => destino(la, lo, rumbo, m);
const aLonLat = ([la, lo]) => [lo, la];

test("proyecta un punto sobre la ruta: avance, restante y distancia lateral", () => {
  const ruta = new Recorrido([aLonLat([LAT, LON]), aLonLat(al(0, 1000))]);
  assert.ok(Math.abs(ruta.total - 1000) < 1);
  const [la, lo] = al(90, 20, al(0, 300));                 // 300 m al norte, 20 m al este
  const p = ruta.proyectar(la, lo);
  assert.ok(Math.abs(p.avance_m - 300) < 2 && Math.abs(p.lateral_m - 20) < 1 && Math.abs(p.restante_m - 700) < 2, JSON.stringify(p));
});

test("antes del inicio y después del final el avance se limita a la ruta", () => {
  const ruta = new Recorrido([aLonLat([LAT, LON]), aLonLat(al(0, 500))]);
  const a = ruta.proyectar(...al(180, 100));
  assert.equal(Math.round(a.avance_m), 0);
  assert.ok(Math.abs(a.lateral_m - 100) < 1);
  const b = ruta.proyectar(...al(0, 600));
  assert.equal(Math.round(b.restante_m), 0);
});

test("si la ruta pasa dos veces por el mismo sitio, sigue el tramo en el que va", () => {
  // sube 400 m, gira al este 100 m, baja 400 m hacia el sur (a 100 m de la subida) y luego vuelve a la subida
  const a = [LAT, LON], b = al(0, 400), c = al(90, 100, b), d = al(180, 400, c);
  const ruta = new Recorrido([a, b, c, d].map(aLonLat));
  const ida = ruta.proyectar(...al(0, 200));
  assert.ok(ida.avance_m < 250);
  const vuelta = ruta.proyectar(...al(180, 200, c));        // en el tramo de bajada
  assert.ok(vuelta.avance_m > 600, `avance ${vuelta.avance_m}`);
});

test("el simulador avanza a velocidad constante aunque la ruta tenga muchos vértices", () => {
  const pts = [];
  for (let i = 0; i <= 100; i++) pts.push(al(0, i * 5));     // vértices cada 5 m
  const lecturas = [...lecturasSimuladas(pts, 36, 1)];       // 10 m/s
  assert.ok(lecturas.length >= 49 && lecturas.length <= 52, `n=${lecturas.length}`);
  const d = distancia(lecturas[0].lat, lecturas[0].lon, lecturas[10].lat, lecturas[10].lon);
  assert.ok(Math.abs(d - 100) < 1, `d=${d}`);
});

test("datosDeRuta alimenta al motor: avisa de los baches y de la zona de la ruta", () => {
  const [zl, zo] = al(0, 400);
  const anillo = [al(270, 40, al(0, 300)), al(90, 40, al(0, 300)), al(90, 40, al(0, 500)), al(270, 40, al(0, 500)), al(270, 40, al(0, 300))].map(aLonLat);
  const resultado = {
    baches: [{ id: 1, lat: al(0, 150)[0], lon: al(0, 150)[1], severidad: "alta" }, { id: 2, lat: zl, lon: zo, severidad: "media" }],
    zonas: [{ geometry: { type: "Polygon", coordinates: [anillo] }, n: 12, alta: 4, media: 5, baja: 3, tramo: "Av. X", ciudad: "Y", lat: zl, lon: zo }],
  };
  const motor = new Motor(...Object.values(datosDeRuta(resultado)));
  const avisos = [];
  for (const p of lecturasSimuladas([[LAT, LON], al(0, 700)], 40)) avisos.push(...motor.actualizar(p).avisos);
  assert.deepEqual(avisos.map((a) => a.tipo), ["bache", "zona"]);
  assert.equal(avisos[1].n, 12);
});

test("textos de distancia y tiempo", () => {
  assert.equal(textoDistancia(850), "850 m");
  assert.match(textoDistancia(4250), /^4,3 km$|^4\.3 km$|^4,2 km$|^4\.2 km$/);
  assert.equal(textoTiempo(25), "1 min");
  assert.equal(textoTiempo(2700), "45 min");
  assert.equal(textoTiempo(5400), "1 h 30 min");
});
