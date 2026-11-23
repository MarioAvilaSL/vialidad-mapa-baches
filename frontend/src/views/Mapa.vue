<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster";
import "leaflet.markercluster/dist/MarkerCluster.css";
import { api } from "../api.js";
import { cargarAjustesServidor, servidor } from "../ajustesServidor.js";
import { useRoute } from "vue-router";
import { ORDEN_SEV, SEV, esc, fechaLocal } from "../mapa/utilidades.js";
import PanelFiltros from "../components/PanelFiltros.vue";
import PanelBache from "../components/PanelBache.vue";

// Mosaicos del mapa. Por defecto, los de OpenStreetMap (gratuitos, para uso moderado). Se puede cambiar creando
// frontend/.env con VITE_TILES_URL=... (por ejemplo, un servidor de mosaicos propio).
const TILES = import.meta.env.VITE_TILES_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const VISTA_INICIAL = [[-5.0, -81.1], [1.5, -75.2]];   // Ecuador, mientras no haya datos que encuadrar

// Los parámetros de las zonas críticas parten de los ajustes guardados (sección Ajustes); aquí se pueden explorar al vuelo.
const filtrosPorDefecto = () => ({
  desde: "", hasta: "", confianza_min: 0, severidad: [...ORDEN_SEV], origen: ["foto", "video"],
  ciudad: "", tramo: "", zonas: true,
  eps_m: servidor.valores.eps_m, min_vecinos: servidor.valores.min_vecinos, min_baches: servidor.valores.min_baches,
});
const ruta = useRoute();
const filtros = reactive(filtrosPorDefecto());
const opciones = ref(null);
const tz = ref("America/Guayaquil");
const mostrados = ref(0);
const totalFiltrado = ref(0);
const truncado = ref(false);
const nZonas = ref(0);
const mayorZona = ref(0);
const cargando = ref(false);
const error = ref("");
const seleccionado = ref(null);
const movil = window.matchMedia("(max-width: 760px)").matches;
const filtrosAbiertos = ref(!movil);

let mapa, grupo, capaZonas, capaInsignias, resaltado, ticket = 0, temporizador = null;
const ZOOM_INSIGNIAS = 13;     // por debajo de este zoom las insignias se montan sobre las agrupaciones

const sinDatos = computed(() => opciones.value && opciones.value.total === 0);

// ── consulta ────────────────────────────────────────────────────────────────
function parametros() {
  const f = filtros, p = new URLSearchParams();
  if (f.desde) p.set("desde", f.desde);
  if (f.hasta) p.set("hasta", f.hasta);
  if (f.confianza_min > 0) p.set("confianza_min", f.confianza_min);
  if (f.severidad.length < 3) f.severidad.forEach((s) => p.append("severidad", s));
  if (f.origen.length < 2) f.origen.forEach((o) => p.append("origen", o));
  if (f.ciudad) p.set("ciudad", f.ciudad);
  if (f.tramo) p.set("tramo", f.tramo);
  return p;
}

async function cargar(encuadrar = false) {
  const mi = ++ticket;                       // si llega una respuesta vieja, se descarta
  error.value = "";
  const vacio = !filtros.severidad.length || !filtros.origen.length;
  if (vacio) {
    pintarBaches({ features: [], total: 0 });
    pintarZonas(null);
    return;
  }
  cargando.value = true;
  try {
    const p = parametros();
    const pz = new URLSearchParams(p);
    pz.set("eps_m", filtros.eps_m);
    pz.set("min_vecinos", filtros.min_vecinos);
    pz.set("min_baches", filtros.min_baches);
    const [g, z] = await Promise.all([api(`/baches?${p}`), filtros.zonas ? api(`/zonas?${pz}`) : null]);
    if (mi !== ticket) return;
    pintarBaches(g);
    pintarZonas(z);
    if (encuadrar) encuadrarTodo();
    actualizarInsignias();
  } catch (e) {
    if (mi === ticket) error.value = "No se pudieron cargar los baches. ¿Está en marcha el servidor?";
  } finally {
    if (mi === ticket) cargando.value = false;
  }
}

// ── dibujo ──────────────────────────────────────────────────────────────────
function pintarBaches(g) {
  grupo.clearLayers();
  const marcas = g.features.map((f) => {
    const [lon, lat] = f.geometry.coordinates;
    const p = f.properties, s = SEV[p.severidad] ?? SEV.baja;
    const m = L.circleMarker([lat, lon], {
      radius: s.radio, color: "#ffffff", weight: 1.5, fillColor: s.color, fillOpacity: 0.92, sev: p.severidad ?? "baja",
    });
    m.bindTooltip(`${s.etiqueta} · ${fechaLocal(p.fecha, tz.value)}`, { direction: "top" });
    m.on("click", () => seleccionar(p.id, [lat, lon]));
    return m;
  });
  grupo.addLayers(marcas);
  mostrados.value = g.features.length;
  totalFiltrado.value = g.total;
  truncado.value = !!g.truncado;
}

function pintarZonas(z) {
  capaZonas.clearLayers();
  capaInsignias.clearLayers();
  nZonas.value = z?.features?.length ?? 0;
  mayorZona.value = z?.features?.[0]?.properties?.n ?? 0;
  if (!z) return;
  L.geoJSON(z, {
    pane: "zonas",
    style: () => ({ color: "#7c3aed", weight: 2, dashArray: "6 4", fillColor: "#7c3aed", fillOpacity: 0.16 }),
    onEachFeature: (f, capa) => capa.bindPopup(htmlZona(f.properties)),
  }).addTo(capaZonas);
  z.features.forEach((f) => {
    const p = f.properties;
    L.marker([p.lat, p.lon], {
      // Encima de las agrupaciones y algo por encima del centro de la zona, para que se pueda pulsar
      icon: L.divIcon({ className: "zona-badge", html: `<b>⚠ ${p.n}</b>`, iconSize: [46, 24], iconAnchor: [23, 42] }),
      zIndexOffset: 10000,
      title: `Zona crítica: ${p.n} baches`,
    }).bindPopup(htmlZona(p)).addTo(capaInsignias);
  });
}

function actualizarInsignias() {
  const ver = mapa.getZoom() >= ZOOM_INSIGNIAS;
  if (ver && !mapa.hasLayer(capaInsignias)) capaInsignias.addTo(mapa);
  if (!ver && mapa.hasLayer(capaInsignias)) capaInsignias.remove();
}

function htmlZona(p) {
  const lugar = [p.tramo, p.ciudad].filter(Boolean).map(esc).join(" · ");
  return `<div class="pop-zona"><strong>Zona crítica · ${p.n} baches</strong>${lugar ? `<br>${lugar}` : ""}
    <br>${p.alta} alta · ${p.media} media · ${p.baja} baja
    <br><small>Vistos en ${p.registros} registro${p.registros === 1 ? "" : "s"} (foto o video). Un mismo bache grabado varias veces cuenta varias veces.</small></div>`;
}

async function seleccionar(id, latlng) {
  try {
    seleccionado.value = await api(`/baches/${id}`);
    if (resaltado) resaltado.remove();
    resaltado = L.circleMarker(latlng, { radius: 17, color: "#0e7c86", weight: 3, fill: false, interactive: false }).addTo(mapa);
    mapa.panTo(latlng);
    if (movil) filtrosAbiertos.value = false;
  } catch {
    error.value = "No se pudo cargar el detalle de ese bache.";
  }
}

function cerrarDetalle() {
  seleccionado.value = null;
  if (resaltado) { resaltado.remove(); resaltado = null; }
}

function encuadrarTodo() {
  const b = grupo.getBounds();
  if (b.isValid()) mapa.fitBounds(b.pad(0.12), { maxZoom: 17 });
}

function restablecer() {
  Object.assign(filtros, filtrosPorDefecto());
}

// ── ciclo de vida ───────────────────────────────────────────────────────────
function iconoCluster(cl) {
  let peor = "baja";
  for (const h of cl.getAllChildMarkers()) {
    if (h.options.sev === "alta") { peor = "alta"; break; }
    if (h.options.sev === "media") peor = "media";
  }
  const n = cl.getChildCount(), t = n < 10 ? 36 : n < 100 ? 44 : 52;
  return L.divIcon({ html: `<div class="cl cl-${peor}"><span>${n}</span></div>`, className: "cl-wrap", iconSize: [t, t] });
}

onMounted(async () => {
  mapa = L.map("mapa", { zoomControl: false, preferCanvas: true }).fitBounds(VISTA_INICIAL);
  L.control.zoom({ position: "bottomright" }).addTo(mapa);
  L.control.scale({ position: "bottomright", imperial: false }).addTo(mapa);
  L.tileLayer(TILES, {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
  }).addTo(mapa);
  if (import.meta.env.DEV) window.__prueba = { mapa: () => mapa, grupo: () => grupo };   // solo en desarrollo: lo usan las pruebas
  mapa.createPane("zonas").style.zIndex = 350;      // las zonas quedan debajo de los marcadores
  capaZonas = L.featureGroup().addTo(mapa);
  capaInsignias = L.featureGroup();
  mapa.on("zoomend", actualizarInsignias);
  grupo = L.markerClusterGroup({
    maxClusterRadius: 45, showCoverageOnHover: false, spiderfyOnMaxZoom: true, chunkedLoading: true,
    iconCreateFunction: iconoCluster,
  }).addTo(mapa);

  try {
    const [o, c] = await Promise.all([api("/baches/filtros"), api("/config"), cargarAjustesServidor()]);
    opciones.value = o;
    tz.value = c.timezone || tz.value;
  } catch { /* el error se muestra al cargar los baches */ }
  Object.assign(filtros, filtrosPorDefecto());
  // Enlaces desde Estadísticas: #/mapa?ciudad=…&tramo=…&lat=…&lon=…
  const q = ruta.query;
  if (typeof q.ciudad === "string") filtros.ciudad = q.ciudad;
  if (typeof q.tramo === "string") filtros.tramo = q.tramo;
  const lat = Number(q.lat), lon = Number(q.lon);
  const centrar = q.lat !== undefined && q.lon !== undefined && Number.isFinite(lat) && Number.isFinite(lon);
  await cargar(!centrar);
  if (centrar) mapa.setView([lat, lon], 17);
  actualizarInsignias();

  watch(filtros, () => {                            // cambios de filtros: se espera un instante para no saturar
    clearTimeout(temporizador);
    temporizador = setTimeout(() => cargar(false), 300);
  }, { deep: true });
});

onBeforeUnmount(() => {
  clearTimeout(temporizador);
  ticket++;
  if (mapa) mapa.remove();
});
</script>

<template>
  <div class="mapa-wrap">
    <div id="mapa" role="application" aria-label="Mapa de baches"></div>

    <button v-if="!filtrosAbiertos" class="btn-filtros" @click="filtrosAbiertos = true">
      ☰ Filtros <span class="cuenta-mini">{{ mostrados }}</span>
    </button>
    <PanelFiltros v-if="filtrosAbiertos" :filtros="filtros" :opciones="opciones" :mostrados="mostrados" :total="opciones?.total"
                  :truncado="truncado" :cargando="cargando"
                  @cerrar="filtrosAbiertos = false" @restablecer="restablecer" @encuadrar="encuadrarTodo" />
    <PanelBache v-if="seleccionado" :bache="seleccionado" :tz="tz" @cerrar="cerrarDetalle" />

    <div v-if="error" class="msg msg-error" role="alert">{{ error }} <button @click="cargar(false)">Reintentar</button></div>
    <div v-else-if="sinDatos" class="msg">
      Aún no hay baches importados. Ve a <RouterLink to="/actualizacion">Actualizar</RouterLink> y pulsa
      «Actualizar mapas de registros».
    </div>
    <div v-else-if="opciones && !cargando && !mostrados" class="msg">Ningún bache cumple estos filtros.</div>
    <div v-if="filtros.zonas && nZonas && !seleccionado && !(movil && filtrosAbiertos)" class="msg msg-zonas">⚠ {{ nZonas }} zona{{ nZonas === 1 ? "" : "s" }} crítica{{ nZonas === 1 ? "" : "s" }} · la mayor: {{ mayorZona }} baches</div>
  </div>
</template>

<style scoped>
.mapa-wrap { position: relative; height: 100%; width: 100%; min-height: 320px; }
#mapa { position: absolute; inset: 0; background: #dfe7ea; }
.btn-filtros { position: absolute; z-index: 1000; top: 12px; left: 12px; background: var(--superficie); color: var(--texto);
  border: 1px solid var(--borde); border-radius: 10px; padding: .55rem .9rem; font: inherit; font-weight: 600; cursor: pointer;
  box-shadow: 0 3px 12px rgba(0, 0, 0, .25); }
.cuenta-mini { background: var(--marca); color: #fff; border-radius: 99px; font-size: .75rem; padding: .1rem .5rem; margin-left: .3rem; }
.msg { position: absolute; z-index: 1000; left: 50%; top: 14px; transform: translateX(-50%); background: var(--superficie); color: var(--texto);
  border: 1px solid var(--borde); border-radius: 10px; padding: .6rem 1rem; box-shadow: 0 3px 12px rgba(0, 0, 0, .25); font-size: .9rem; max-width: min(520px, 90%); text-align: center; }
.msg-error { background: var(--aviso-fondo); }
.msg-zonas { top: auto; bottom: 28px; font-weight: 600; color: #7c3aed; }
.msg button { margin-left: .5rem; }
@media (max-width: 760px) {
  .msg { top: 64px; }
  .msg.msg-zonas { top: auto; bottom: 74px; }
}
</style>
