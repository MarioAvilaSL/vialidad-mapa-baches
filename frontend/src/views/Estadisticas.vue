<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { api } from "../api.js";
import { ORDEN_SEV, SEV } from "../mapa/utilidades.js";

const filtros = reactive({ desde: "", hasta: "", ciudad: "" });
const opciones = ref(null);
const d = ref(null);
const cargando = ref(false);
const error = ref("");
let ticket = 0, temporizador = null;

const consulta = () => {
  const p = new URLSearchParams();
  for (const k of ["desde", "hasta", "ciudad"]) if (filtros[k]) p.set(k, filtros[k]);
  return p.toString();
};

async function cargar() {
  const mi = ++ticket;
  cargando.value = true; error.value = "";
  try {
    const r = await api(`/estadisticas?${consulta()}`);
    if (mi === ticket) d.value = r;
  } catch (e) {
    if (mi === ticket) error.value = "No se pudieron cargar las estadísticas. ¿Está en marcha el servidor?";
  } finally {
    if (mi === ticket) cargando.value = false;
  }
}

onMounted(async () => {
  try { opciones.value = await api("/baches/filtros"); } catch { /* se avisa al cargar */ }
  cargar();
  watch(filtros, () => { clearTimeout(temporizador); temporizador = setTimeout(cargar, 250); });
});

const hayFiltros = computed(() => !!(filtros.desde || filtros.hasta || filtros.ciudad));
const pct = (n, t) => (t ? Math.round((100 * n) / t) : 0);
const fechaCorta = (iso) => (iso ? new Date(iso + "T12:00:00").toLocaleDateString("es-EC", { day: "numeric", month: "short", year: "numeric" }) : "—");
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const etiquetaMes = (m) => `${MESES[+m.slice(5) - 1]} ${m.slice(2, 4)}`;

// Barras por mes (SVG): cada barra apila alta, media y baja
const grafico = computed(() => {
  const meses = d.value?.por_mes ?? [];
  const max = Math.max(1, ...meses.map((m) => m.n));
  const ancho = 46, alto = 170, arriba = 20;
  return {
    w: Math.max(meses.length * ancho, 300), h: alto + arriba + 22, max, arriba,
    barras: meses.map((m, i) => {
      let y = alto;
      const trozos = ["baja", "media", "alta"].map((s) => {
        const h = (m[s] / max) * alto;
        y -= h;
        return { s, y, h, n: m[s] };
      });
      return { ...m, x: i * ancho + 8, ancho: ancho - 16, trozos, ytop: y, etiqueta: etiquetaMes(m.mes) };
    }),
    alto,
  };
});

const enlaceMapa = (q) => ({ path: "/mapa", query: q });
</script>

<template>
  <section class="vista">
    <h1>Estadísticas</h1>

    <div class="tarjeta filtros">
      <label>Desde <input type="date" v-model="filtros.desde" :min="opciones?.fecha_min" :max="filtros.hasta || opciones?.fecha_max" /></label>
      <label>Hasta <input type="date" v-model="filtros.hasta" :min="filtros.desde || opciones?.fecha_min" :max="opciones?.fecha_max" /></label>
      <label>Ciudad
        <select v-model="filtros.ciudad">
          <option value="">Todas</option>
          <option v-for="c in opciones?.ciudades ?? []" :key="c.nombre" :value="c.nombre">{{ c.nombre }} ({{ c.n }})</option>
        </select>
      </label>
      <button v-if="hayFiltros" class="boton sec" @click="Object.assign(filtros, { desde: '', hasta: '', ciudad: '' })">Quitar filtros</button>
      <span v-if="cargando" class="suave">Actualizando…</span>
    </div>

    <p v-if="error" class="tarjeta aviso">{{ error }}</p>

    <p v-else-if="d && d.total === 0" class="tarjeta suave">
      No hay baches {{ hayFiltros ? "con estos filtros" : "importados todavía" }}.
      <router-link v-if="!hayFiltros" to="/actualizacion">Importar desde el proyecto original</router-link>
    </p>

    <template v-else-if="d">
      <div class="cuadricula kpis">
        <div class="tarjeta cifra"><span class="suave">Baches</span><strong>{{ d.total.toLocaleString("es-EC") }}</strong>
          <small>{{ fechaCorta(d.fecha_min) }} – {{ fechaCorta(d.fecha_max) }}</small></div>
        <div class="tarjeta cifra"><span class="suave">Origen</span><strong class="origen">{{ d.por_origen.video }} <small>videos</small> · {{ d.por_origen.foto }} <small>fotos</small></strong>
          <small>{{ pct(d.con_evidencia, d.total) }} % con imagen de evidencia</small></div>
        <div class="tarjeta cifra"><span class="suave">Confianza media</span><strong>{{ d.confianza_media == null ? "—" : Math.round(d.confianza_media * 100) + " %" }}</strong>
          <small>de la detección</small></div>
        <div class="tarjeta cifra"><span class="suave">En zonas críticas</span><strong>{{ d.zonas.baches_en_zonas }}</strong>
          <small>{{ d.zonas.total }} zona{{ d.zonas.total === 1 ? "" : "s" }} · {{ pct(d.zonas.baches_en_zonas, d.total) }} % de los baches</small></div>
      </div>

      <h2>Severidad estimada</h2>
      <div class="tarjeta">
        <div class="apilada" role="img" :aria-label="`Alta ${d.por_severidad.alta}, media ${d.por_severidad.media}, baja ${d.por_severidad.baja}`">
          <span v-for="s in ORDEN_SEV" :key="s" :style="{ width: pct(d.por_severidad[s], d.total) + '%', background: SEV[s].color }"></span>
        </div>
        <ul class="leyenda">
          <li v-for="s in ORDEN_SEV" :key="s"><i :style="{ background: SEV[s].color }"></i>{{ SEV[s].etiqueta }}: <b>{{ d.por_severidad[s] }}</b> ({{ pct(d.por_severidad[s], d.total) }} %)</li>
        </ul>
        <p class="suave nota">La severidad es una estimación a partir del tamaño relativo, la confianza y la persistencia; no es una medición vial.</p>
      </div>

      <h2>Baches por mes</h2>
      <div class="tarjeta desplaza">
        <svg v-if="grafico.barras.length" :viewBox="`0 0 ${grafico.w} ${grafico.h}`" :width="grafico.w" :height="grafico.h" role="img"
             aria-label="Baches detectados por mes, apilados por severidad">
          <g :transform="`translate(0 ${grafico.arriba})`">
          <g v-for="b in grafico.barras" :key="b.mes">
            <title>{{ b.etiqueta }}: {{ b.n }} baches ({{ b.alta }} alta, {{ b.media }} media, {{ b.baja }} baja)</title>
            <rect v-for="t in b.trozos" :key="t.s" :x="b.x" :y="t.y" :width="b.ancho" :height="t.h" :fill="SEV[t.s].color" />
            <text :x="b.x + b.ancho / 2" :y="b.ytop - 4" text-anchor="middle" class="svg-n">{{ b.n }}</text>
            <text :x="b.x + b.ancho / 2" :y="grafico.alto + 15" text-anchor="middle" class="svg-m">{{ b.etiqueta }}</text>
          </g>
          <line x1="0" :x2="grafico.w" :y1="grafico.alto" :y2="grafico.alto" class="svg-eje" />
          </g>
        </svg>
        <p v-else class="suave">Los baches no tienen fecha.</p>
      </div>

      <div class="dos">
        <div>
          <h2>Calles o tramos con más baches</h2>
          <div class="tarjeta">
            <table v-if="d.por_tramo.length">
              <thead><tr><th>Calle o tramo</th><th class="n">Baches</th><th>Severidad</th><th></th></tr></thead>
              <tbody>
                <tr v-for="t in d.por_tramo" :key="t.nombre + t.ciudad">
                  <td>{{ t.nombre }}<br /><small class="suave">{{ t.ciudad }}</small></td>
                  <td class="n"><b>{{ t.n }}</b></td>
                  <td><div class="mini"><span v-for="s in ORDEN_SEV" :key="s" :style="{ width: pct(t[s], t.n) + '%', background: SEV[s].color }" :title="`${SEV[s].etiqueta}: ${t[s]}`"></span></div></td>
                  <td><router-link :to="enlaceMapa({ tramo: t.nombre, ciudad: t.ciudad || undefined })">Ver en el mapa</router-link></td>
                </tr>
              </tbody>
            </table>
            <p v-else class="suave">Ningún bache tiene nombre de calle.</p>
            <p v-if="d.sin_calle" class="suave nota">{{ d.sin_calle }} baches no tienen nombre de calle y no aparecen aquí.</p>
          </div>
        </div>
        <div>
          <h2>Ciudades</h2>
          <div class="tarjeta">
            <table v-if="d.por_ciudad.length">
              <thead><tr><th>Ciudad</th><th class="n">Baches</th><th>Severidad</th><th></th></tr></thead>
              <tbody>
                <tr v-for="c in d.por_ciudad" :key="c.nombre">
                  <td>{{ c.nombre }}</td>
                  <td class="n"><b>{{ c.n }}</b></td>
                  <td><div class="mini"><span v-for="s in ORDEN_SEV" :key="s" :style="{ width: pct(c[s], c.n) + '%', background: SEV[s].color }" :title="`${SEV[s].etiqueta}: ${c[s]}`"></span></div></td>
                  <td><router-link :to="enlaceMapa({ ciudad: c.nombre })">Ver en el mapa</router-link></td>
                </tr>
              </tbody>
            </table>
            <p v-else class="suave">Ningún bache tiene ciudad.</p>
          </div>
        </div>
      </div>

      <h2>Zonas críticas principales</h2>
      <div class="tarjeta">
        <p class="suave nota" style="margin-top:0">
          Parámetros vigentes: cercanía {{ d.zonas.parametros.eps_m }} m, densidad {{ d.zonas.parametros.min_vecinos }}, tamaño mínimo {{ d.zonas.parametros.min_baches }} baches.
          <router-link to="/configuracion">Cambiar en Ajustes</router-link>
        </p>
        <table v-if="d.zonas.principales.length">
          <thead><tr><th>Zona</th><th class="n">Baches</th><th>Severidad</th><th class="n" title="Fotos o videos distintos en los que se ven">Registros</th><th></th></tr></thead>
          <tbody>
            <tr v-for="(z, i) in d.zonas.principales" :key="i">
              <td>{{ z.tramo || "Sin nombre de calle" }}<br /><small class="suave">{{ z.ciudad }}</small></td>
              <td class="n"><b>{{ z.n }}</b></td>
              <td><div class="mini"><span v-for="s in ORDEN_SEV" :key="s" :style="{ width: pct(z[s], z.n) + '%', background: SEV[s].color }" :title="`${SEV[s].etiqueta}: ${z[s]}`"></span></div></td>
              <td class="n">{{ z.registros }}</td>
              <td><router-link :to="enlaceMapa({ lat: z.lat, lon: z.lon })">Ver en el mapa</router-link></td>
            </tr>
          </tbody>
        </table>
        <p v-else class="suave">Con estos parámetros no hay zonas críticas.</p>
        <p class="suave nota">Un mismo bache grabado en varios recorridos cuenta varias veces: una zona con pocos registros distintos suele ser un único punto repetido.</p>
      </div>
    </template>
  </section>
</template>

<style scoped>
.filtros { display: flex; flex-wrap: wrap; gap: .8rem 1.2rem; align-items: end; margin-bottom: 1rem; }
.filtros label { display: flex; flex-direction: column; gap: .2rem; font-size: .8rem; color: var(--suave); }
.filtros input, .filtros select { font: inherit; padding: .35rem .5rem; border-radius: 8px; border: 1px solid var(--borde); background: var(--fondo); color: var(--texto); }
.boton.sec { background: var(--fondo); color: var(--texto); border: 1px solid var(--borde); }
.kpis .cifra strong { font-size: 1.8rem; }
.kpis small { font-size: .78rem; }
.kpis .origen { font-size: 1.25rem; white-space: nowrap; }
.apilada { display: flex; height: 22px; border-radius: 6px; overflow: hidden; background: var(--borde); }
.leyenda { list-style: none; padding: 0; margin: .7rem 0 0; display: flex; flex-wrap: wrap; gap: .4rem 1.4rem; }
.leyenda i { display: inline-block; width: .8rem; height: .8rem; border-radius: 50%; margin-right: .4rem; }
.nota { font-size: .8rem; margin: .7rem 0 0; }
.desplaza { overflow-x: auto; }
.svg-n { font-size: 11px; fill: var(--texto); font-weight: 600; }
.svg-m { font-size: 11px; fill: var(--suave); }
.svg-eje { stroke: var(--borde); }
.dos { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 0 1.2rem; align-items: start; }
table { width: 100%; border-collapse: collapse; font-size: .88rem; }
th { text-align: left; font-size: .74rem; color: var(--suave); font-weight: 600; padding: 0 .4rem .4rem 0; }
td { padding: .45rem .4rem .45rem 0; border-top: 1px solid var(--borde); vertical-align: middle; }
.n { text-align: right; padding-right: .8rem; }
.mini { display: flex; width: 90px; height: 10px; border-radius: 4px; overflow: hidden; background: var(--borde); }
@media (max-width: 760px) { .dos { grid-template-columns: 1fr; } .mini { width: 60px; } }
</style>
