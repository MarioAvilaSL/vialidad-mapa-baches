<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { api } from "../api.js";

const salud = ref(null);
const actual = ref(null);       // importación mostrada (en curso o la última)
const historial = ref([]);
const errores = ref(null);
const verErrores = ref(false);
const aviso = ref("");
let timer = null;

const enCurso = computed(() => actual.value?.estado === "en_curso");
const origenListo = computed(() => salud.value?.origen?.alcanzable);
const progreso = computed(() => {
  const a = actual.value;
  if (!a || !a.encontrados) return 0;
  return Math.min(100, Math.round((a.procesados / a.encontrados) * 100));
});

const fecha = (iso) => (iso ? new Date(iso).toLocaleString("es-EC") : "—");

async function cargarEstado() {
  try {
    salud.value = await api("/health");
    historial.value = await api("/importaciones?limit=8");
    if (!actual.value && historial.value.length) {
      actual.value = historial.value[0];
      if (actual.value.estado === "en_curso") vigilar();
    }
  } catch {
    aviso.value = "No se pudo contactar con el servidor. ¿Está en marcha el backend (puerto 8001)?";
  }
}

async function actualizar() {
  aviso.value = "";
  errores.value = null;
  verErrores.value = false;
  try {
    const { id } = await api("/importaciones", { method: "POST" });
    actual.value = { id, estado: "en_curso", encontrados: 0, procesados: 0 };
    vigilar();
  } catch (e) {
    aviso.value = e.message.replace(/^\d+: /, "");
  }
}

function vigilar() {
  clearInterval(timer);
  timer = setInterval(async () => {
    try {
      actual.value = await api(`/importaciones/${actual.value.id}`);
      if (actual.value.estado !== "en_curso") {
        clearInterval(timer);
        historial.value = await api("/importaciones?limit=8");
        if (actual.value.omitidos + actual.value.errores > 0) errores.value = await api(`/importaciones/${actual.value.id}/errores`);
      }
    } catch { /* se reintenta en el siguiente ciclo */ }
  }, 800);
}

async function mostrarErrores() {
  verErrores.value = !verErrores.value;
  if (verErrores.value && !errores.value) errores.value = await api(`/importaciones/${actual.value.id}/errores`);
}

onMounted(cargarEstado);
onUnmounted(() => clearInterval(timer));
</script>

<template>
  <section class="vista">
    <h1>Actualizar mapas de registros</h1>
    <p class="suave intro">
      Lee del proyecto Vialidad · YOLO los baches nuevos o cambiados (solo la clase <i>pothole</i>) y los incorpora al mapa.
      El proyecto original no se modifica. La actualización es manual: solo ocurre cuando pulsas el botón.
    </p>

    <div v-if="aviso" class="tarjeta aviso"><p>{{ aviso }}</p></div>

    <div v-if="salud && !origenListo" class="tarjeta aviso">
      <p><b>El proyecto original no está disponible.</b>
        {{ salud.origen.configurado ? salud.origen.detalle : "Falta configurar ORIGEN_DATABASE_URL en backend/.env (ver README, paso 4)." }}</p>
    </div>
    <div v-else-if="salud && !salud.origen.storage" class="tarjeta nota">
      <p><b>Las imágenes de evidencia no se copiarán.</b> Falta <code>ORIGEN_STORAGE_DIR</code> en backend/.env (la carpeta
        <code>storage</code> del proyecto original). Puedes actualizar igual y, cuando la configures, volver a pulsar el botón:
        las imágenes pendientes se completan.</p>
    </div>

    <button class="boton grande" :disabled="enCurso || !origenListo" @click="actualizar">
      {{ enCurso ? "Actualizando…" : "Actualizar mapas de registros" }}
    </button>

    <div v-if="actual" class="tarjeta resultado">
      <div class="cabecera">
        <strong>Actualización n.º {{ actual.id }}</strong>
        <span class="chip" :class="actual.estado">{{ { en_curso: "En curso", completada: "Completada", fallida: "Fallida" }[actual.estado] }}</span>
      </div>

      <div v-if="enCurso" class="barra" role="progressbar" :aria-valuenow="progreso" aria-valuemin="0" aria-valuemax="100">
        <div :style="{ width: progreso + '%' }"></div>
        <span>{{ actual.encontrados ? `${actual.procesados} de ${actual.encontrados}` : "Leyendo el proyecto original…" }}</span>
      </div>

      <p v-if="actual.estado === 'fallida'" class="error">{{ actual.mensaje }}</p>

      <template v-if="actual.estado === 'completada'">
        <p class="suave">{{ fecha(actual.iniciada_en) }}</p>
        <div class="cifras">
          <div><strong>{{ actual.encontrados }}</strong><small>Encontrados</small></div>
          <div class="bien"><strong>{{ actual.nuevos }}</strong><small>Nuevos</small></div>
          <div><strong>{{ actual.actualizados }}</strong><small>Actualizados</small></div>
          <div><strong>{{ actual.sin_cambios }}</strong><small>Duplicados<br />(ya importados)</small></div>
          <div><strong>{{ actual.descartados }}</strong><small>Descartados<br />en el original</small></div>
          <div :class="{ aten: actual.omitidos }"><strong>{{ actual.omitidos }}</strong><small>Sin GPS válido<br />(omitidos)</small></div>
          <div :class="{ mal: actual.errores }"><strong>{{ actual.errores }}</strong><small>Errores</small></div>
        </div>
        <p class="suave pie">
          Encontrados = nuevos + actualizados + duplicados + descartados + sin GPS + errores.
          <template v-if="actual.retirados"> · {{ actual.retirados }} ya no existen en el original (se conservan marcados).</template>
          <template v-if="actual.sin_evidencia"> · {{ actual.sin_evidencia }} sin imagen de evidencia.</template>
        </p>

        <button v-if="actual.omitidos + actual.errores > 0" class="enlace-btn" @click="mostrarErrores">
          {{ verErrores ? "Ocultar" : "Ver" }} los {{ actual.omitidos + actual.errores }} registros no importados
        </button>
        <div v-if="verErrores && errores" class="detalle">
          <ul class="motivos">
            <li v-for="(n, m) in errores.por_motivo" :key="m"><b>{{ n }}</b> · {{ m }}</li>
          </ul>
          <details v-if="errores.registros.length">
            <summary>Lista (primeros {{ errores.registros.length }})</summary>
            <table>
              <tr v-for="(r, i) in errores.registros" :key="i">
                <td>{{ r.origen_tipo === "foto" ? "Foto (detección" : "Video (hallazgo" }} {{ r.origen_id }})</td><td>{{ r.motivo }}</td>
              </tr>
            </table>
          </details>
        </div>
      </template>
    </div>

    <template v-if="historial.length">
      <h2>Historial</h2>
      <div class="tarjeta tabla">
        <table>
          <thead><tr><th>N.º</th><th>Fecha</th><th>Estado</th><th>Nuevos</th><th>Actualiz.</th><th>Sin GPS</th><th>Errores</th></tr></thead>
          <tbody>
            <tr v-for="h in historial" :key="h.id">
              <td>{{ h.id }}</td><td>{{ fecha(h.iniciada_en) }}</td><td>{{ h.estado.replace("_", " ") }}</td>
              <td>{{ h.nuevos }}</td><td>{{ h.actualizados }}</td><td>{{ h.omitidos }}</td><td>{{ h.errores }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<style scoped>
.intro { max-width: 62ch; margin-top: -.4rem; }
.grande { font-size: 1.05rem; padding: .8rem 1.6rem; margin: .4rem 0 1.2rem; }
.boton:disabled { opacity: .5; cursor: not-allowed; }
.nota { background: var(--superficie); border-style: dashed; margin-bottom: 1rem; }
code { background: var(--fondo); padding: .05rem .35rem; border-radius: 5px; font-size: .85em; }
.cabecera { display: flex; justify-content: space-between; align-items: center; gap: .6rem; margin-bottom: .6rem; }
.chip { font-size: .75rem; font-weight: 600; padding: .15rem .65rem; border-radius: 99px; background: var(--borde); }
.chip.completada { background: var(--ok); color: #fff; }
.chip.fallida { background: var(--mal); color: #fff; }
.chip.en_curso { background: var(--marca); color: #fff; }
.barra { position: relative; height: 1.6rem; background: var(--fondo); border-radius: 99px; overflow: hidden; border: 1px solid var(--borde); }
.barra div { height: 100%; background: var(--marca); transition: width .3s; }
.barra span { position: absolute; inset: 0; display: grid; place-items: center; font-size: .8rem; font-weight: 600; mix-blend-mode: difference; color: #fff; }
.error { color: var(--mal); font-weight: 600; }
.cifras { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: .7rem; margin: .8rem 0; }
.cifras div { background: var(--fondo); border-radius: 10px; padding: .7rem .8rem; display: flex; flex-direction: column; }
.cifras strong { font-size: 1.7rem; line-height: 1.1; }
.cifras small { font-size: .74rem; line-height: 1.25; margin-top: .2rem; }
.cifras .bien strong { color: var(--ok); }
.cifras .aten strong { color: #b45309; }
.cifras .mal strong { color: var(--mal); }
.pie { font-size: .85rem; margin: .4rem 0; }
.enlace-btn { background: none; border: 0; color: var(--marca); font: inherit; font-weight: 600; cursor: pointer; padding: .3rem 0; text-decoration: underline; }
.detalle { margin-top: .5rem; }
.motivos { margin: .3rem 0 .6rem; padding-left: 1.1rem; }
table { width: 100%; border-collapse: collapse; font-size: .88rem; }
td, th { padding: .35rem .5rem; text-align: left; border-bottom: 1px solid var(--borde); }
.tabla { padding: .4rem .8rem; overflow-x: auto; }
details { margin-top: .4rem; max-height: 260px; overflow: auto; }
</style>
