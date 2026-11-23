<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { api } from "../api.js";
import { iniciarGps, abrirAjustesUbicacion } from "../plataforma/gps.js";
import { mantenerPantalla } from "../plataforma/voz.js";
import { guardarLocal, leerLocal } from "../plataforma/datosLocales.js";
import { hayServidor } from "../plataforma/servidor.js";
import { ajustes } from "../conduccion/ajustes.js";
import { Motor, lecturasSimuladas, rutaPorZona, textoAviso } from "../conduccion/motor.js";
import { Recorrido, datosDeRuta, textoDistancia } from "../conduccion/ruta.js";
import PlanificadorRuta from "../components/PlanificadorRuta.vue";
import { detenerVoz, emitir, prepararAudio } from "../conduccion/avisos.js";
import { registrar } from "../conduccion/historial.js";
import { SEV } from "../mapa/utilidades.js";

const TILES = import.meta.env.VITE_TILES_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

const cargando = ref(true);
const error = ref("");
const nBaches = ref(0);
const zonas = ref([]);                 // [{i, n, tramo, ciudad}] para elegir en el simulador
const conduciendo = ref(false);
const simulado = ref(false);
const velSim = ref(40);
const aceleracion = ref(1);
const zonaSim = ref(0);
const estado = ref(null);
const avisoActual = ref(null);
const mensajeGps = ref("");
const fin = ref(false);
const planificando = ref(false);
const vista = ref(null);                // límites de los baches, para centrar el planificador
const rutaActiva = ref(null);           // {resultado, indice} cuando se conduce con una ruta planificada
const progreso = ref(null);             // {lateral_m, avance_m, restante_m, fuera}
const llegado = ref(false);
const recalculando = ref(false);
const origenDatos = ref(null);          // {tipo: 'servidor' | 'local', fecha} de dónde salen los baches cargados
const rutaGuardada = ref(null);         // última ruta planificada (guardada en el dispositivo)
const falloPermiso = ref(false);

let motor = null, motorRuta = null, recorrido = null, capaRuta = null, posActual = null, datos = null, detenerGps = null, tempSim = null, tempAviso = null, liberarPantalla = null;
let mapa = null, capaPos = null, ultimaPos = null, capaBaches = null;

// ── datos ───────────────────────────────────────────────────────────────────
function instalarDatos(b, z) {
  datos = { baches: b, zonas: z };
  motor = new Motor(b, z, ajustes);
  nBaches.value = b.features.length;
  zonas.value = motor.zonas.map((x) => ({ i: x.i, n: x.n, tramo: x.tramo, ciudad: x.ciudad }));
  zonaSim.value = zonas.value[0]?.i ?? 0;
  const lat = b.features.map((f) => f.geometry.coordinates[1]), lon = b.features.map((f) => f.geometry.coordinates[0]);
  vista.value = lat.length ? [[Math.min(...lat), Math.min(...lon)], [Math.max(...lat), Math.max(...lon)]] : null;
}

// Primero se piden los datos al servidor (y se guarda una copia en el dispositivo); si no responde, se usa la copia.
async function cargar() {
  cargando.value = true; error.value = "";
  rutaGuardada.value = await leerLocal("ruta");
  try {
    if (!hayServidor()) throw Object.assign(new Error("sin servidor"), { sinConexion: true });
    const [b, z] = await Promise.all([api("/baches?limit=50000"), api("/zonas")]);      // zonas con los ajustes guardados
    instalarDatos(b, z);
    const fecha = new Date().toISOString();
    origenDatos.value = { tipo: "servidor", fecha };
    guardarLocal("conduccion", { baches: b, zonas: z, fecha });
  } catch (e) {
    const copia = await leerLocal("conduccion");
    if (copia) {
      instalarDatos(copia.baches, copia.zonas);
      origenDatos.value = { tipo: "local", fecha: copia.fecha };
    } else if (!hayServidor()) {
      error.value = "Falta indicar dónde está el servidor. Ve a Ajustes → Conexión.";
    } else {
      error.value = `No se pudieron cargar los baches: ${e.detalle || e.message}. Se necesita conexión con el servidor al menos una vez para guardar los datos en el dispositivo.`;
    }
  } finally {
    cargando.value = false;
  }
}
watch(() => [ajustes.radio_m, ajustes.nivel_min, ajustes.zonas], () => { motor?.setAjustes(ajustes); motorRuta?.setAjustes(ajustes); });
watch(() => ajustes.nivel_min, () => dibujarBaches());

// ── mapa pequeño ────────────────────────────────────────────────────────────
function montarMapa() {
  mapa = L.map("mapa-cond", { zoomControl: false, preferCanvas: true, attributionControl: true });
  L.tileLayer(TILES, { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OSM</a>' }).addTo(mapa);
  // Leaflet necesita una vista inicial antes de añadir capas vectoriales
  const b = L.geoJSON(datos.baches).getBounds();
  mapa.fitBounds(b.isValid() ? b.pad(0.1) : [[-5.0, -81.1], [1.5, -75.2]]);
  L.geoJSON(datos.zonas, { style: { color: "#7c3aed", weight: 2, fillOpacity: 0.18, dashArray: "5 4" }, interactive: false }).addTo(mapa);
  capaBaches = null;
  dibujarBaches();
  capaPos = null;
}
// Solo se dibujan los baches de la severidad elegida en Ajustes → Alertas (o en el selector de esta pantalla)
function dibujarBaches() {
  if (!mapa || !datos) return;
  capaBaches?.remove();
  const minimo = { baja: 1, media: 2, alta: 3 }[ajustes.nivel_min] ?? 1;
  const rango = { baja: 1, media: 2, alta: 3 };
  capaBaches = L.layerGroup();
  for (const f of datos.baches.features) {
    if ((rango[f.properties.severidad] ?? 1) < minimo) continue;
    const s = SEV[f.properties.severidad] || SEV.baja;
    L.circleMarker([f.geometry.coordinates[1], f.geometry.coordinates[0]], {
      radius: s.radio - 1, color: "#fff", weight: 1.5, fillColor: s.color, fillOpacity: 0.95, interactive: false,
    }).addTo(capaBaches);
  }
  capaBaches.addTo(mapa);
}
function dibujarRuta() {
  if (!mapa || !rutaActiva.value) return;
  capaRuta?.remove();
  const ru = rutaActiva.value.resultado.rutas[rutaActiva.value.indice];
  capaRuta = L.geoJSON(ru.geometria, { style: { color: "#2563eb", weight: 6, opacity: 0.8 }, interactive: false }).addTo(mapa);
  capaRuta.bringToBack?.();
}
function moverMapa(p, rumbo) {
  if (!mapa) return;
  const icono = L.divIcon({
    className: "yo-wrap", iconSize: [34, 34],
    html: `<div class="yo" style="transform:rotate(${Math.round(rumbo ?? 0)}deg)">▲</div>`,
  });
  if (!capaPos) capaPos = L.marker([p.lat, p.lon], { icon: icono, zIndexOffset: 5000, interactive: false }).addTo(mapa);
  else capaPos.setLatLng([p.lat, p.lon]).setIcon(icono);
  if (!ultimaPos) mapa.setView([p.lat, p.lon], 17); else mapa.panTo([p.lat, p.lon], { animate: true, duration: 0.5 });
  ultimaPos = p;
}

// ── proceso de una lectura ──────────────────────────────────────────────────
function prepararRuta() {
  const ru = rutaActiva.value.resultado.rutas[rutaActiva.value.indice];
  recorrido = new Recorrido(ru.geometria.coordinates);
  const d = datosDeRuta(ru);
  motorRuta = new Motor(d.baches, d.zonas, ajustes);
  progreso.value = null;
}

function procesar(pos) {
  if (llegado.value) return;
  posActual = pos;
  let r = motor.actualizar(pos);
  if (recorrido) {
    const pr = recorrido.proyectar(pos.lat, pos.lon);
    const rr = motorRuta.actualizar(pos);          // los dos motores ven todas las lecturas: así no repiten avisos al cambiar
    const fuera = progreso.value?.fuera ? pr.lateral_m > 30 : pr.lateral_m > 60;    // histéresis
    progreso.value = { ...pr, fuera };
    if (!fuera) r = rr;
    if (pr.restante_m < 25 && pr.avance_m > recorrido.total * 0.5) {
      llegado.value = true;
      const a = { tipo: "llegada", sev: "baja", n: 1, distancia: 0, lat: pos.lat, lon: pos.lon, t: pos.t };
      registrar(a, textoAviso(a), simulado.value);
      emitir(a, ajustes);
      clearInterval(tempSim);
      detenerGps?.(); detenerGps = null;
      estado.value = r.estado; moverMapa(pos, r.estado.rumbo);
      return;
    }
  }
  estado.value = r.estado;
  mensajeGps.value = r.estado.debil ? "Señal GPS débil: esperando mejor precisión…" : "";
  if (r.avisos.length) {
    for (const a of r.avisos) registrar(a, textoAviso(a), simulado.value);
    const a = r.avisos[0];
    const texto = emitir(a, ajustes);
    avisoActual.value = { ...a, texto };
    clearTimeout(tempAviso);
    tempAviso = setTimeout(() => { avisoActual.value = null; }, 9000);
  }
  moverMapa(pos, r.estado.rumbo);
}

async function recalcular() {
  if (!posActual || !rutaActiva.value || recalculando.value) return;
  recalculando.value = true;
  try {
    const r = await api("/rutas/planificar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ origen: { lat: posActual.lat, lon: posActual.lon }, destino: rutaActiva.value.resultado.destino, alternativas: 1 }),
    });
    rutaActiva.value = { resultado: r, indice: r.recomendada };
    prepararRuta();
    dibujarRuta();
  } catch (e) {
    mensajeGps.value = `No se pudo recalcular la ruta: ${e.detalle || e.message}`;
  } finally {
    recalculando.value = false;
  }
}

async function bloquearPantalla() {
  liberarPantalla?.();
  liberarPantalla = await mantenerPantalla();
}
const alVolver = () => { if (conduciendo.value && document.visibilityState === "visible") bloquearPantalla(); };

async function iniciar(esSimulacion, ruta = null) {
  if (!motor) return;
  prepararAudio();
  motor.reiniciar();
  simulado.value = esSimulacion; fin.value = false;
  estado.value = null; avisoActual.value = null; mensajeGps.value = ""; ultimaPos = null;
  llegado.value = false; progreso.value = null; posActual = null;
  rutaActiva.value = ruta;
  recorrido = null; motorRuta = null;
  if (ruta) prepararRuta();
  conduciendo.value = true;
  await nextTick();
  if (ajustes.mapa) { montarMapa(); dibujarRuta(); }
  bloquearPantalla();

  if (esSimulacion) {
    const trayecto = ruta
      ? ruta.resultado.rutas[ruta.indice].geometria.coordinates.map(([lo, la]) => [la, lo])
      : rutaPorZona(motor, zonaSim.value);
    if (!trayecto) { error.value = "Esa zona no tiene baches suficientes para simular un recorrido."; detener(); return; }
    const it = lecturasSimuladas(trayecto, velSim.value, 1);
    tempSim = setInterval(() => {
      const n = it.next();
      if (n.done) { fin.value = true; clearInterval(tempSim); return; }
      procesar(n.value);
    }, 1000 / aceleracion.value);
    return;
  }
  mensajeGps.value = "Buscando señal GPS…";
  falloPermiso.value = false;
  try {
    detenerGps = await iniciarGps(procesar, (msg, tipo) => { mensajeGps.value = msg; falloPermiso.value = tipo === "permiso"; });
  } catch (e) {
    mensajeGps.value = e.message;
  }
}

function detener() {
  conduciendo.value = false;
  detenerGps?.(); detenerGps = null;
  clearInterval(tempSim); clearTimeout(tempAviso);
  detenerVoz();
  liberarPantalla?.(); liberarPantalla = null;
  if (mapa) { mapa.remove(); mapa = null; capaPos = null; capaRuta = null; }
  estado.value = null; avisoActual.value = null; progreso.value = null; rutaActiva.value = null; recorrido = null; motorRuta = null;
}

function desdePlanificador(e) {
  planificando.value = false;
  const guardada = { resultado: e.resultado, indice: e.indice, guardada: new Date().toISOString() };
  rutaGuardada.value = guardada;
  guardarLocal("ruta", guardada);
  velSim.value = e.velocidad; aceleracion.value = e.aceleracion;
  iniciar(e.simular, { resultado: e.resultado, indice: e.indice });
}

function usarRutaGuardada(simular) {
  const g = rutaGuardada.value;
  if (g) iniciar(simular, { resultado: g.resultado, indice: g.indice });
}
const fechaCorta = (iso) => (iso ? new Date(iso).toLocaleString("es-EC", { timeZone: "America/Guayaquil", dateStyle: "short", timeStyle: "short" }) : "");

// ── lo que se ve ────────────────────────────────────────────────────────────
const redondear = (m) => (m < 25 ? Math.max(10, Math.round(m / 5) * 5) : Math.round(m / 10) * 10);
const panel = computed(() => {
  const e = estado.value, a = avisoActual.value;
  if (llegado.value) return { clase: "libre", titulo: "Llegaste a tu destino", detalle: "Pulsa Detener para terminar." };
  if (mensajeGps.value && (!e || e.debil)) return { clase: "gris", titulo: mensajeGps.value };
  if (a) {
    if (a.tipo === "zona") return { clase: "zona", titulo: "ZONA CRÍTICA", metros: a.dentro ? null : redondear(a.distancia), detalle: `${a.n} baches${a.tramo ? " · " + a.tramo : ""}` };
    return { clase: "sev-" + a.sev, titulo: a.n === 1 ? `BACHE ${SEV[a.sev].etiqueta.toUpperCase()}` : `${a.n} BACHES`, metros: redondear(a.distancia), detalle: "" };
  }
  if (!e) return { clase: "gris", titulo: simulado.value ? "Iniciando simulación…" : "Esperando ubicación…" };
  if (progreso.value?.fuera && !e.zona) return { clase: "gris", titulo: "Fuera de la ruta", detalle: "Se avisa de todos los baches cercanos.", recalcular: true };
  if (e.zona) return { clase: "zona", titulo: "EN ZONA CRÍTICA", detalle: `${e.zona.n} baches${e.zona.tramo ? " · " + e.zona.tramo : ""}. Conduce con precaución.` };
  if (e.proximo) {
    const p = e.proximo;
    return { clase: "sev-" + p.sev, titulo: p.tipo === "zona" ? "Zona crítica adelante" : p.n === 1 ? "Bache adelante" : `${p.n} baches adelante`, metros: redondear(p.distancia), detalle: "" };
  }
  return { clase: "libre", titulo: "Vía despejada", detalle: e.parado ? "Detenido" : (siguienteEnRuta.value || "Sin baches registrados cerca") };
});
// Lo próximo que hay en la ruta, para mirar un instante cuando no hay avisos
const siguienteEnRuta = computed(() => {
  const pr = progreso.value;
  if (!pr || !rutaActiva.value) return "";
  const ru = rutaActiva.value.resultado.rutas[rutaActiva.value.indice];
  const z = ru.zonas.find((x) => x.desde_m > pr.avance_m + 20);
  if (z) return `Próxima zona crítica en ${textoDistancia(z.desde_m - pr.avance_m)}`;
  const b = ru.baches.find((x) => x.desde_m > pr.avance_m + 20);
  return b ? `Próximo bache en ${textoDistancia(b.desde_m - pr.avance_m)}` : "No quedan baches registrados en la ruta";
});
const quedan = computed(() => (progreso.value ? `Quedan ${textoDistancia(progreso.value.restante_m)}` : ""));
const kmh = computed(() => (estado.value?.velocidad == null ? "—" : Math.round(estado.value.velocidad * 3.6)));

onMounted(() => { cargar(); document.addEventListener("visibilitychange", alVolver); });
onBeforeUnmount(() => { detener(); document.removeEventListener("visibilitychange", alVolver); });
</script>

<template>
  <div class="cond" :class="{ activa: conduciendo }">
    <!-- Preparación -->
    <div v-if="!conduciendo" class="prep">
      <h1>Modo de conducción</h1>
      <p v-if="cargando" class="suave">Cargando baches…</p>
      <p v-else-if="error" class="error">{{ error }}</p>
      <template v-else>
        <div class="tarjeta">
          <p style="margin-top:0"><b>{{ nBaches }}</b> baches y <b>{{ zonas.length }}</b> zona{{ zonas.length === 1 ? "" : "s" }} crítica{{ zonas.length === 1 ? "" : "s" }} cargados en este dispositivo.</p>
          <p v-if="origenDatos?.tipo === 'local'" class="aviso-local">Sin conexión con el servidor: se usan los datos guardados en este dispositivo el {{ fechaCorta(origenDatos.fecha) }}.
            <button class="enlace-btn" @click="cargar">Reintentar</button></p>
          <p v-else-if="origenDatos" class="suave" style="margin:.2rem 0"><small>Datos del servidor (copia guardada en este dispositivo).</small></p>
          <label class="campo" style="margin:.4rem 0">Mostrar y avisar baches de severidad
            <select v-model="ajustes.nivel_min">
              <option value="baja">Todas (baja, media y alta)</option>
              <option value="media">Media y alta</option>
              <option value="alta">Solo alta</option>
            </select>
          </label>
          <p class="suave">Avisará de baches a <b>{{ ajustes.radio_m }} m</b> (severidad
            {{ ajustes.nivel_min === "baja" ? "cualquiera" : ajustes.nivel_min === "media" ? "media y alta" : "alta" }}) y de zonas críticas {{ ajustes.zonas ? "activado" : "desactivado" }}.
            <router-link to="/alertas">Cambiar ajustes</router-link></p>
          <button class="boton grande" @click="iniciar(false)">▶ Iniciar con GPS</button>
          <p class="suave"><small>Mantén la pantalla encendida y el teléfono sujeto. Los avisos son por zona de la vía: el GPS no distingue carriles ni la posición exacta del bache.</small></p>
        </div>
        <div class="tarjeta">
          <h2 style="margin-top:0">Ruta de A a B</h2>
          <p class="suave" style="margin-top:0">Elige origen y destino, compara rutas según los baches que cruzan y conduce con avisos de lo que hay en tu camino.</p>
          <button class="boton" @click="planificando = true">⇄ Planificar ruta</button>
          <div v-if="rutaGuardada" class="ruta-guardada">
            <p style="margin:.2rem 0"><b>Última ruta planificada</b> · {{ fechaCorta(rutaGuardada.guardada) }}<br />
              <small class="suave">{{ textoDistancia(rutaGuardada.resultado.rutas[rutaGuardada.indice].distancia_m) }} ·
                {{ rutaGuardada.resultado.rutas[rutaGuardada.indice].resumen.zonas }} zonas críticas ·
                {{ rutaGuardada.resultado.rutas[rutaGuardada.indice].resumen.baches }} baches. Funciona sin conexión.</small></p>
            <button class="boton sec" @click="usarRutaGuardada(false)">▶ Conducir con esta ruta</button>
            <button class="boton sec" @click="usarRutaGuardada(true)">Simular</button>
          </div>
        </div>
        <div class="tarjeta">
          <h2 style="margin-top:0">Probar sin conducir</h2>
          <template v-if="zonas.length">
            <label class="campo">Recorrer la zona
              <select v-model.number="zonaSim">
                <option v-for="z in zonas" :key="z.i" :value="z.i">{{ z.tramo || "Sin nombre" }}{{ z.ciudad ? " · " + z.ciudad : "" }} ({{ z.n }} baches)</option>
              </select>
            </label>
            <label class="campo"><span>Velocidad simulada: <b>{{ velSim }} km/h</b></span>
        <input type="range" min="20" max="90" step="5" v-model.number="velSim" />
            </label>
            <label class="campo">Rapidez de la prueba
              <select v-model.number="aceleracion"><option :value="1">Tiempo real</option><option :value="4">4 veces más rápida</option></select>
            </label>
            <button class="boton sec" @click="iniciar(true)">▶ Simular recorrido</button>
          </template>
          <p v-else class="suave">No hay zonas críticas para simular con los valores actuales.</p>
        </div>
      </template>
    </div>

    <!-- Conduciendo -->
    <template v-else>
      <div v-show="ajustes.mapa" id="mapa-cond" class="mapa-cond"></div>
      <div class="superior" :class="panel.clase" role="status" aria-live="assertive">
        <div class="titulo">{{ panel.titulo }}</div>
        <div v-if="panel.metros != null" class="metros">{{ panel.metros }} <small>m</small></div>
        <div v-if="panel.detalle" class="detalle">{{ panel.detalle }}</div>
        <div v-if="mensajeGps && estado && !estado.debil" class="detalle">{{ mensajeGps }}</div>
        <button v-if="falloPermiso" class="recalc" @click="abrirAjustesUbicacion">Abrir ajustes de ubicación</button>
        <button v-if="panel.recalcular && !simulado" class="recalc" :disabled="recalculando" @click="recalcular">{{ recalculando ? "Calculando…" : "Recalcular ruta desde aquí" }}</button>
      </div>
      <div class="inferior">
        <div class="vel"><b>{{ kmh }}</b> km/h<span v-if="quedan" class="quedan">{{ quedan }}</span><span v-if="simulado" class="sim">simulación</span></div>
        <div v-if="fin" class="fin">Recorrido terminado</div>
        <button class="mini" :class="{ off: !ajustes.voz }" @click="ajustes.voz = !ajustes.voz" :aria-pressed="ajustes.voz" aria-label="Voz">🔊</button>
        <button class="detener" @click="detener">■ Detener</button>
      </div>
    </template>

    <PlanificadorRuta v-if="planificando && !conduciendo" :vista="vista" @cerrar="planificando = false" @iniciar="desdePlanificador" />
  </div>
</template>

<style scoped>
.cond { position: relative; height: 100%; overflow: auto; }
.cond.activa { overflow: hidden; background: #0b1620; }
.prep { padding: 1.6rem 1.8rem; max-width: 640px; display: grid; gap: 1rem; align-content: start; }
.prep h1 { margin: 0; }
.error { color: var(--mal); }
.campo { display: flex; flex-direction: column; gap: .25rem; color: var(--suave); font-size: .9rem; margin-bottom: .7rem; }
.campo b { color: var(--texto); }
.campo select { font: inherit; padding: .4rem .5rem; border-radius: 8px; border: 1px solid var(--borde); background: var(--fondo); color: var(--texto); }
.campo input[type="range"] { accent-color: var(--marca); }
.boton.grande { font-size: 1.15rem; padding: .8rem 1.4rem; }
.boton.sec { background: var(--fondo); color: var(--texto); border: 1px solid var(--borde); }
.ruta-guardada { margin-top: .8rem; padding-top: .6rem; border-top: 1px solid var(--borde); display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
.ruta-guardada p { flex-basis: 100%; }
.aviso-local { background: var(--aviso-fondo); border-radius: 8px; padding: .5rem .7rem; margin: 0 0 .6rem; }
.enlace-btn { background: none; border: 0; color: var(--marca-fuerte); font: inherit; text-decoration: underline; cursor: pointer; padding: 0; }

.mapa-cond { position: absolute; inset: 0; z-index: 0; }
.superior { position: absolute; z-index: 1000; top: 10px; left: 10px; right: 10px; border-radius: 16px; padding: .8rem 1.2rem;
  color: #fff; text-align: center; box-shadow: 0 6px 24px rgba(0, 0, 0, .35); transition: background .2s; }
.superior .titulo { font-size: clamp(1.3rem, 4.5vw, 2rem); font-weight: 800; letter-spacing: .02em; }
.superior .metros { font-size: clamp(3rem, 14vw, 5.5rem); font-weight: 800; line-height: 1; }
.superior .metros small { font-size: .35em; font-weight: 600; color: inherit; }
.superior .detalle { font-size: 1.05rem; opacity: .95; margin-top: .2rem; }
.libre { background: rgba(10, 93, 101, .94); }
.gris { background: rgba(60, 76, 86, .95); }
.zona { background: rgba(109, 40, 217, .96); }
.sev-alta { background: rgba(200, 30, 30, .96); }
.sev-media { background: rgba(200, 120, 0, .96); }
.sev-baja { background: rgba(30, 120, 50, .96); }
.inferior { position: absolute; z-index: 1000; left: 10px; right: 10px; bottom: 10px; display: flex; align-items: center; gap: .6rem;
  background: rgba(11, 22, 32, .92); color: #fff; border-radius: 16px; padding: .6rem .8rem; }
.vel { font-size: 1.1rem; margin-right: auto; }
.vel b { font-size: 2rem; }
.sim { margin-left: .6rem; font-size: .7rem; border: 1px solid #5b7280; border-radius: 99px; padding: 0 .5rem; color: #b7c9d3; }
.fin { color: #46c9d4; font-weight: 600; }
.quedan { margin-left: .8rem; font-size: .95rem; color: #b7c9d3; }
.recalc { margin-top: .5rem; background: #fff; color: #0b1f2a; border: 0; border-radius: 10px; font: inherit; font-weight: 700; padding: .5rem 1rem; cursor: pointer; }
.recalc:disabled { opacity: .6; }
.mini { background: #1e3846; border: 0; color: #fff; border-radius: 10px; font-size: 1.3rem; padding: .45rem .7rem; cursor: pointer; }
.mini.off { opacity: .4; }
.detener { background: #b91c1c; color: #fff; border: 0; border-radius: 12px; font: inherit; font-weight: 700; font-size: 1.1rem; padding: .7rem 1.3rem; cursor: pointer; }
@media (max-width: 760px) { .prep { padding: 1.1rem 1rem 5rem; } .inferior { bottom: 8px; } }
</style>
<style>
.yo-wrap { background: transparent; }
.yo { width: 34px; height: 34px; display: grid; place-items: center; font-size: 26px; color: #0e7c86; text-shadow: 0 0 3px #fff, 0 0 3px #fff, 0 0 6px #fff; }
</style>
