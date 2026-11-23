<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { api } from "../api.js";
import { textoDistancia, textoTiempo } from "../conduccion/ruta.js";
import { SEV } from "../mapa/utilidades.js";

const props = defineProps({ vista: Array });          // [[latMin, lonMin], [latMax, lonMax]] de los baches cargados
const emit = defineEmits(["cerrar", "iniciar"]);

const TILES = import.meta.env.VITE_TILES_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
// Buscador de direcciones: Nominatim (OpenStreetMap), gratuito y sin clave. Solo se consulta al pulsar «Buscar»
// (su política de uso prohíbe autocompletar y uso intensivo). Se puede cambiar con VITE_GEOCODER_URL.
const GEOCODER = import.meta.env.VITE_GEOCODER_URL || "https://nominatim.openstreetmap.org/search";

const motor = ref(null);                  // estado del motor de rutas
const origen = ref(null), destino = ref(null);                 // {lat, lon}
const texto = ref({ origen: "", destino: "" });
const sugerencias = ref({ origen: [], destino: [] });
const buscando = ref("");
const calculando = ref(false);
const error = ref("");
const resultado = ref(null);
const elegida = ref(0);
const velSim = ref(40);
const aceleracion = ref(4);
const panelAbierto = ref(true);

let mapa = null, marcas = {}, capaRutas = null, capaPeligros = null;

// ── mapa ────────────────────────────────────────────────────────────────────
function crearMapa() {
  mapa = L.map("mapa-plan", { zoomControl: false, preferCanvas: true });
  L.control.zoom({ position: "bottomright" }).addTo(mapa);
  L.tileLayer(TILES, { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OSM</a>' }).addTo(mapa);
  mapa.fitBounds(props.vista || [[-5.0, -81.1], [1.5, -75.2]]);
  capaRutas = L.layerGroup().addTo(mapa);
  capaPeligros = L.layerGroup().addTo(mapa);
  mapa.on("click", (e) => {
    if (!origen.value) fijar("origen", e.latlng.lat, e.latlng.lng);
    else if (!destino.value) fijar("destino", e.latlng.lat, e.latlng.lng);
  });
}

function icono(letra, color) {
  return L.divIcon({ className: "punto-wrap", iconSize: [32, 32], iconAnchor: [16, 16],
    html: `<div class="punto-ab" style="background:${color}">${letra}</div>` });
}

function fijar(cual, lat, lon, centrar = false) {
  const p = { lat, lon };
  if (cual === "origen") origen.value = p; else destino.value = p;
  texto.value[cual] = texto.value[cual] || `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
  if (marcas[cual]) marcas[cual].setLatLng([lat, lon]);
  else {
    marcas[cual] = L.marker([lat, lon], { draggable: true, icon: icono(cual === "origen" ? "A" : "B", cual === "origen" ? "#0e7c86" : "#b91c1c"), zIndexOffset: 1000 }).addTo(mapa);
    marcas[cual].on("dragend", () => {
      const q = marcas[cual].getLatLng();
      fijar(cual, q.lat, q.lng);
      texto.value[cual] = `${q.lat.toFixed(5)}, ${q.lng.toFixed(5)}`;
    });
  }
  if (centrar) mapa.setView([lat, lon], Math.max(mapa.getZoom(), 15));
  limpiarResultado();
}

function quitar(cual) {
  if (cual === "origen") origen.value = null; else destino.value = null;
  texto.value[cual] = "";
  if (marcas[cual]) { marcas[cual].remove(); delete marcas[cual]; }
  limpiarResultado();
}

function limpiarResultado() {
  resultado.value = null; error.value = "";
  capaRutas?.clearLayers(); capaPeligros?.clearLayers();
}

// ── buscar direcciones y ubicación actual ───────────────────────────────────
async function buscar(cual) {
  const q = texto.value[cual].trim();
  if (q.length < 3) return;
  buscando.value = cual; error.value = ""; sugerencias.value[cual] = [];
  try {
    const url = `${GEOCODER}?${new URLSearchParams({ q, format: "jsonv2", limit: "5", countrycodes: "ec", "accept-language": "es" })}`;
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const lista = await r.json();
    sugerencias.value[cual] = lista.map((x) => ({ nombre: x.display_name, lat: +x.lat, lon: +x.lon }));
    if (!lista.length) error.value = `No se encontró «${q}». Prueba con otra dirección o pulsa el punto en el mapa.`;
  } catch (e) {
    error.value = `No se pudo buscar la dirección (${e.message}). Puedes elegir el punto pulsando en el mapa.`;
  } finally {
    buscando.value = "";
  }
}
function elegirSugerencia(cual, s) {
  texto.value[cual] = s.nombre.split(",").slice(0, 2).join(",");
  sugerencias.value[cual] = [];
  fijar(cual, s.lat, s.lon, true);
}
function miUbicacion() {
  if (!("geolocation" in navigator) || !window.isSecureContext) {
    error.value = "La ubicación del navegador solo funciona con https o en localhost. Elige el origen en el mapa o escribe una dirección.";
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (p) => { texto.value.origen = "Mi ubicación"; fijar("origen", p.coords.latitude, p.coords.longitude, true); },
    (e) => { error.value = e.code === 1 ? "Permiso de ubicación denegado." : "No se pudo obtener tu ubicación."; },
    { enableHighAccuracy: true, timeout: 15000 },
  );
}

// ── calcular y mostrar ──────────────────────────────────────────────────────
async function calcular() {
  if (!origen.value || !destino.value) return;
  calculando.value = true; error.value = ""; resultado.value = null;
  try {
    const r = await api("/rutas/planificar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ origen: origen.value, destino: destino.value, alternativas: 3 }),
    });
    resultado.value = r;
    elegida.value = r.recomendada;
    dibujar(true);
  } catch (e) {
    error.value = e.detalle || e.message;
  } finally {
    calculando.value = false;
  }
}

function dibujar(ajustar) {
  capaRutas.clearLayers(); capaPeligros.clearLayers();
  const r = resultado.value;
  if (!r) return;
  r.rutas.forEach((ru, i) => {
    if (i === elegida.value) return;
    L.geoJSON(ru.geometria, { style: { color: "#6b7f8c", weight: 5, opacity: 0.75 } }).on("click", () => { elegida.value = i; }).addTo(capaRutas);
  });
  const sel = r.rutas[elegida.value];
  const linea = L.geoJSON(sel.geometria, { style: { color: "#0e7c86", weight: 7, opacity: 0.95 } }).addTo(capaRutas);
  for (const z of sel.zonas) L.geoJSON(z.geometry, { style: { color: "#7c3aed", weight: 2, fillOpacity: 0.22, dashArray: "5 4" } })
    .bindPopup(`<b>Zona crítica</b><br>${z.n} baches · ${textoDistancia(z.desde_m)} desde el inicio`).addTo(capaPeligros);
  for (const b of sel.baches) {
    const s = SEV[b.severidad] || SEV.baja;
    L.circleMarker([b.lat, b.lon], { radius: s.radio - 1, color: "#fff", weight: 1.5, fillColor: s.color, fillOpacity: 0.95 }).addTo(capaPeligros);
  }
  if (ajustar) mapa.fitBounds(linea.getBounds().pad(0.15));
}
watch(elegida, () => dibujar(false));

const etiqueta = (i) => {
  const r = resultado.value;
  if (i === r.recomendada && i === r.mas_rapida) return "Recomendada y más rápida";
  if (i === r.recomendada) return "Recomendada: menos baches";
  if (i === r.mas_rapida) return "Más rápida";
  return "Alternativa";
};
const resumen = computed(() => {
  const r = resultado.value?.rutas[elegida.value];
  if (!r) return "";
  const s = r.resumen;
  if (!s.baches && !s.zonas) return "Sin baches registrados a lo largo de esta ruta.";
  const partes = [];
  if (s.zonas) partes.push(`cruza ${s.zonas} zona${s.zonas === 1 ? "" : "s"} crítica${s.zonas === 1 ? "" : "s"} (la primera a ${textoDistancia(r.zonas[0].desde_m)})`);
  partes.push(`${s.baches} bache${s.baches === 1 ? "" : "s"} cerca del trayecto (${s.alta} alta, ${s.media} media, ${s.baja} baja)`);
  return partes.join(" y ").replace(/^./, (c) => c.toUpperCase()) + ".";
});

function iniciar(simular) {
  emit("iniciar", { resultado: resultado.value, indice: elegida.value, simular, velocidad: velSim.value, aceleracion: aceleracion.value });
}

async function estadoMotor() {
  try { motor.value = (await api("/rutas/estado")); } catch { motor.value = { disponible: false, detalle: "no se pudo contactar con el servidor" }; }
}

onMounted(() => { crearMapa(); estadoMotor(); });
onBeforeUnmount(() => { mapa?.remove(); mapa = null; });
</script>

<template>
  <div class="plan">
    <div id="mapa-plan" class="mapa"></div>

    <aside class="panel" :class="{ cerrado: !panelAbierto }" aria-label="Planificador de ruta">
      <header>
        <h2>Ruta A → B</h2>
        <button class="x" :aria-label="panelAbierto ? 'Minimizar' : 'Abrir'" @click="panelAbierto = !panelAbierto">{{ panelAbierto ? "–" : "+" }}</button>
        <button class="x" aria-label="Volver" @click="emit('cerrar')">×</button>
      </header>

      <div v-show="panelAbierto" class="cuerpo">
        <p v-if="motor && !motor.disponible" class="aviso">
          El motor de rutas no está en marcha ({{ motor.detalle }}). Instálalo y arráncalo siguiendo
          <b>graphhopper/README.md</b>; después recarga esta página.
        </p>

        <div v-for="cual in ['origen', 'destino']" :key="cual" class="campo">
          <label :for="'q-' + cual"><b>{{ cual === "origen" ? "A · Origen" : "B · Destino" }}</b></label>
          <div class="fila">
            <input :id="'q-' + cual" v-model="texto[cual]" placeholder="Dirección o pulsa en el mapa"
                   @keyup.enter="buscar(cual)" />
            <button class="b" :disabled="buscando === cual" @click="buscar(cual)" title="Buscar dirección">🔍</button>
            <button v-if="cual === 'origen'" class="b" @click="miUbicacion" title="Usar mi ubicación">📍</button>
            <button v-if="(cual === 'origen' ? origen : destino)" class="b" @click="quitar(cual)" title="Quitar">✕</button>
          </div>
          <ul v-if="sugerencias[cual].length" class="sug">
            <li v-for="s in sugerencias[cual]" :key="s.lat + ',' + s.lon" @click="elegirSugerencia(cual, s)">{{ s.nombre }}</li>
          </ul>
        </div>
        <p class="suave ayuda" v-if="!origen || !destino"><small>Escribe una dirección y pulsa 🔍, o pulsa directamente en el mapa: el primer toque pone A y el segundo B. Puedes arrastrar los marcadores.</small></p>

        <button class="boton" :disabled="!origen || !destino || calculando || (motor && !motor.disponible)" @click="calcular">
          {{ calculando ? "Calculando…" : "Calcular ruta" }}
        </button>
        <p v-if="error" class="error" role="alert">{{ error }}</p>

        <template v-if="resultado">
          <ul class="rutas">
            <li v-for="(r, i) in resultado.rutas" :key="i" :class="{ sel: i === elegida }" @click="elegida = i" tabindex="0" @keyup.enter="elegida = i">
              <div class="et">{{ etiqueta(i) }}</div>
              <div class="num"><b>{{ textoTiempo(r.tiempo_s) }}</b> · {{ textoDistancia(r.distancia_m) }}</div>
              <div class="chips">
                <span class="chip" :style="{ background: r.resumen.baches ? '#fdecec' : '#e8f6ec', color: '#222' }">{{ r.resumen.baches }} baches</span>
                <span class="chip z">{{ r.resumen.zonas }} zona{{ r.resumen.zonas === 1 ? "" : "s" }}</span>
                <span v-if="r.resumen.alta" class="chip a">{{ r.resumen.alta }} alta</span>
              </div>
            </li>
          </ul>
          <p class="resumen">{{ resumen }}</p>
          <p v-if="resultado.rutas.length === 1" class="suave"><small>El motor solo encontró una ruta razonable entre estos puntos.</small></p>
          <button class="boton grande" @click="iniciar(false)">▶ Iniciar conducción con esta ruta</button>
          <details class="sim">
            <summary>Probar esta ruta sin conducir</summary>
            <label class="campo2"><span>Velocidad simulada: <b>{{ velSim }} km/h</b></span>
        <input type="range" min="20" max="90" step="5" v-model.number="velSim" /></label>
            <label class="campo2">Rapidez de la prueba
              <select v-model.number="aceleracion"><option :value="1">Tiempo real</option><option :value="4">4 veces más rápida</option><option :value="10">10 veces más rápida</option></select></label>
            <button class="boton sec" @click="iniciar(true)">▶ Simular esta ruta</button>
          </details>
        </template>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.plan { position: absolute; inset: 0; z-index: 1500; background: var(--fondo); }
.mapa { position: absolute; inset: 0; }
.panel { position: absolute; z-index: 1000; top: 12px; left: 12px; width: 340px; max-height: calc(100% - 24px); overflow-y: auto; overflow-x: hidden;
  background: var(--superficie); border: 1px solid var(--borde); border-radius: var(--radio); box-shadow: 0 6px 24px rgba(0, 0, 0, .25); padding: .8rem .95rem 1rem; font-size: .88rem; }
header { display: flex; align-items: center; gap: .3rem; }
h2 { font-size: 1.05rem; margin: 0 auto 0 0; }
.x { background: none; border: 0; font-size: 1.5rem; line-height: 1; color: var(--suave); cursor: pointer; padding: 0 .35rem; }
.cuerpo { display: grid; grid-template-columns: minmax(0, 1fr); gap: .6rem; margin-top: .5rem; }
.campo { display: grid; grid-template-columns: minmax(0, 1fr); gap: .25rem; position: relative; min-width: 0; }
.fila { display: flex; gap: .3rem; }
.fila input { flex: 1; min-width: 0; font: inherit; padding: .4rem .5rem; border-radius: 8px; border: 1px solid var(--borde); background: var(--fondo); color: var(--texto); }
.b { background: var(--fondo); border: 1px solid var(--borde); border-radius: 8px; cursor: pointer; padding: 0 .55rem; color: var(--texto); }
.sug { list-style: none; margin: 0; padding: 0; border: 1px solid var(--borde); border-radius: 8px; max-height: 170px; overflow: auto; background: var(--superficie); }
.sug li { padding: .4rem .55rem; cursor: pointer; border-bottom: 1px solid var(--borde); font-size: .8rem; }
.sug li:hover { background: var(--fondo); }
.ayuda { margin: 0; }
.aviso { background: var(--aviso-fondo); border-radius: 8px; padding: .5rem .65rem; margin: 0; }
.error { color: var(--mal); margin: 0; }
.boton:disabled { opacity: .45; cursor: not-allowed; }
.boton.grande { font-size: 1rem; padding: .7rem 1rem; }
.boton.sec { background: var(--fondo); color: var(--texto); border: 1px solid var(--borde); }
.rutas { list-style: none; margin: 0; padding: 0; display: grid; gap: .4rem; }
.rutas li { border: 2px solid var(--borde); border-radius: 10px; padding: .45rem .65rem; cursor: pointer; }
.rutas li.sel { border-color: var(--marca); background: color-mix(in srgb, var(--marca) 9%, transparent); }
.et { font-size: .74rem; font-weight: 700; color: var(--marca); text-transform: uppercase; letter-spacing: .03em; }
.num { font-size: .95rem; }
.chips { display: flex; gap: .3rem; flex-wrap: wrap; margin-top: .25rem; }
.chip { font-size: .72rem; padding: .05rem .5rem; border-radius: 99px; border: 1px solid var(--borde); }
.chip.z { background: #efe7fd; color: #4c1d95; }
.chip.a { background: #d62828; color: #fff; border-color: #d62828; }
.resumen { margin: 0; }
.sim summary { cursor: pointer; color: var(--suave); }
.campo2 { display: grid; gap: .2rem; color: var(--suave); font-size: .82rem; margin: .5rem 0; }
.campo2 b { color: var(--texto); }
.campo2 select { font: inherit; padding: .3rem; border-radius: 7px; border: 1px solid var(--borde); background: var(--fondo); color: var(--texto); }
.campo2 input[type="range"] { accent-color: var(--marca); }
@media (max-width: 760px) { .panel { top: auto; left: 8px; right: 8px; bottom: 8px; width: auto; max-height: 62%; } }
</style>
<style>
.punto-wrap { background: transparent; }
.punto-ab { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; color: #fff; font-weight: 800;
  border: 3px solid #fff; box-shadow: 0 2px 8px rgba(0, 0, 0, .5); }
</style>
