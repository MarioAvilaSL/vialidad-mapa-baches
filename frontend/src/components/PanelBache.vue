<script setup>
import { ref, watch } from "vue";
import { SEV, fechaLocal, rumboTexto } from "../mapa/utilidades.js";
import { urlRecurso } from "../plataforma/servidor.js";

const props = defineProps({ bache: Object, tz: String });
defineEmits(["cerrar"]);

const fallo = ref(false);
const copiado = ref(false);
watch(() => props.bache?.id, () => { fallo.value = false; copiado.value = false; });

const GPS = { exif: "EXIF de la foto", manual: "Indicada a mano", gpx: "Ruta GPX del video" };

async function copiar() {
  const t = `${props.bache.lat.toFixed(6)}, ${props.bache.lon.toFixed(6)}`;
  try { await navigator.clipboard.writeText(t); copiado.value = true; setTimeout(() => (copiado.value = false), 1500); } catch { /* sin permiso: se ignora */ }
}
</script>

<template>
  <aside v-if="bache" class="panel panel-bache" aria-label="Detalle del bache">
    <header>
      <span class="punto" :style="{ background: SEV[bache.severidad.nivel]?.color }"></span>
      <h2>Bache · severidad {{ SEV[bache.severidad.nivel]?.etiqueta?.toLowerCase() ?? "sin calcular" }}</h2>
      <button class="cerrar" aria-label="Cerrar" @click="$emit('cerrar')">×</button>
    </header>

    <a v-if="bache.evidencia_url && !fallo" :href="urlRecurso(bache.evidencia_url)" target="_blank" rel="noopener" class="foto">
      <img :src="urlRecurso(bache.evidencia_url)" alt="Imagen de evidencia del bache" loading="lazy" @error="fallo = true" />
    </a>
    <p v-else class="sin-foto">Sin imagen de evidencia disponible.</p>

    <dl>
      <dt>Detectado</dt><dd>{{ fechaLocal(bache.detectado_en, tz) }}</dd>
      <dt>Confianza del modelo</dt><dd>{{ Math.round(bache.confianza * 100) }} %</dd>
      <dt>Severidad estimada</dt><dd>{{ bache.severidad.puntaje ?? "—" }} / 100 <small>(heurística)</small></dd>
      <dt>Ubicación</dt>
      <dd>{{ bache.lat.toFixed(6) }}, {{ bache.lon.toFixed(6) }}
        <button class="mini" @click="copiar">{{ copiado ? "Copiado" : "Copiar" }}</button></dd>
      <dt>Calle o tramo</dt><dd>{{ bache.tramo || "—" }}<template v-if="bache.ciudad"> · {{ bache.ciudad }}</template></dd>
      <dt>Origen</dt><dd>{{ bache.origen.tipo === "foto" ? "Foto" : "Video" }} (n.º {{ bache.origen.id }})</dd>
      <dt>Fuente del GPS</dt><dd>{{ GPS[bache.gps_origen] || bache.gps_origen }}</dd>
      <template v-if="bache.rumbo_grados != null"><dt>Sentido de marcha</dt><dd>{{ rumboTexto(bache.rumbo_grados) }}</dd></template>
      <template v-if="bache.n_apariciones"><dt>Visto en</dt><dd>{{ bache.n_apariciones }} fotogramas</dd></template>
      <template v-if="bache.area_frac != null"><dt>Tamaño relativo</dt><dd>{{ (bache.area_frac * 100).toFixed(1) }} % de la imagen</dd></template>
      <template v-if="bache.modelo_version"><dt>Modelo</dt><dd>{{ bache.modelo_version }}<template v-if="bache.perfil"> · perfil {{ bache.perfil }}</template></dd></template>
    </dl>
    <p class="aviso-ub">La ubicación es la de la cámara al registrar el bache; el bache real puede estar unos metros más adelante.</p>
  </aside>
</template>

<style scoped>
.panel { position: absolute; z-index: 1000; background: var(--superficie); border: 1px solid var(--borde); border-radius: var(--radio);
  box-shadow: 0 6px 24px rgba(0, 0, 0, .22); overflow: auto; }
.panel-bache { top: 12px; right: 12px; bottom: 12px; width: 340px; padding: 1rem; }
header { display: flex; align-items: center; gap: .55rem; margin-bottom: .7rem; }
h2 { font-size: 1rem; margin: 0; flex: 1; }
.punto { width: .9rem; height: .9rem; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 0 1px var(--borde); flex-shrink: 0; }
.cerrar { background: none; border: 0; font-size: 1.7rem; line-height: 1; color: var(--suave); cursor: pointer; padding: 0 .3rem; }
.foto img { width: 100%; border-radius: 9px; display: block; background: var(--fondo); }
.sin-foto { background: var(--fondo); border-radius: 9px; padding: 1.2rem; text-align: center; color: var(--suave); font-size: .9rem; margin: 0; }
dl { display: grid; grid-template-columns: auto 1fr; gap: .35rem .8rem; margin: .8rem 0 .4rem; font-size: .88rem; }
dt { color: var(--suave); }
dd { margin: 0; font-weight: 600; word-break: break-word; }
dd small { font-weight: 400; color: var(--suave); }
.mini { margin-left: .3rem; font-size: .72rem; padding: .08rem .5rem; border: 1px solid var(--borde); background: var(--fondo); color: var(--texto); border-radius: 6px; cursor: pointer; }
.aviso-ub { font-size: .78rem; color: var(--suave); margin: .6rem 0 0; }

@media (max-width: 760px) {
  .panel-bache { top: auto; left: 8px; right: 8px; bottom: 8px; width: auto; max-height: 62%; }
  .foto img { max-height: 190px; object-fit: cover; }
}
</style>
