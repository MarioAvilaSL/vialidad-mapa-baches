<script setup>
import { computed } from "vue";
import { ORDEN_SEV, SEV } from "../mapa/utilidades.js";

const props = defineProps({
  filtros: { type: Object, required: true },
  opciones: Object,
  mostrados: Number,
  total: Number,
  truncado: Boolean,
  cargando: Boolean,
});
defineEmits(["restablecer", "cerrar", "encuadrar"]);

const tramos = computed(() => {
  const t = props.opciones?.tramos ?? [];
  return props.filtros.ciudad ? t.filter((x) => x.ciudad === props.filtros.ciudad) : t;
});
const hayFiltros = computed(() => {
  const f = props.filtros;
  return !!(f.desde || f.hasta || f.confianza_min > 0 || f.severidad.length < 3 || f.origen.length < 2 || f.ciudad || f.tramo);
});

function alCambiarCiudad() {
  if (props.filtros.tramo && !tramos.value.some((t) => t.nombre === props.filtros.tramo)) props.filtros.tramo = "";
}
</script>

<template>
  <aside class="panel panel-filtros" aria-label="Filtros del mapa">
    <header>
      <h2>Filtros</h2>
      <button class="cerrar" aria-label="Ocultar filtros" @click="$emit('cerrar')">×</button>
    </header>

    <p class="cuenta" :class="{ cargando }">
      <b>{{ mostrados }}</b> baches<template v-if="hayFiltros && total != null"> de {{ total }}</template> en el mapa
      <template v-if="truncado"> · <i>se muestran solo los más severos</i></template>
    </p>

    <fieldset>
      <legend>Severidad <small>(estimada)</small></legend>
      <label v-for="s in ORDEN_SEV" :key="s" class="chk">
        <input type="checkbox" :value="s" v-model="filtros.severidad" />
        <span class="punto" :style="{ background: SEV[s].color, width: SEV[s].radio + 6 + 'px', height: SEV[s].radio + 6 + 'px' }"></span>
        {{ SEV[s].etiqueta }}
      </label>
    </fieldset>

    <fieldset>
      <legend>Origen del registro</legend>
      <label class="chk"><input type="checkbox" value="foto" v-model="filtros.origen" /> Fotos</label>
      <label class="chk"><input type="checkbox" value="video" v-model="filtros.origen" /> Videos</label>
    </fieldset>

    <label class="campo"><span>Confianza mínima: <b>{{ Math.round(filtros.confianza_min * 100) }} %</b></span>
        <input type="range" min="0" max="95" step="5" :value="filtros.confianza_min * 100"
             @input="filtros.confianza_min = $event.target.value / 100" />
    </label>

    <div class="fila">
      <label class="campo">Desde
        <input type="date" v-model="filtros.desde" :min="opciones?.fecha_min" :max="filtros.hasta || opciones?.fecha_max" />
      </label>
      <label class="campo">Hasta
        <input type="date" v-model="filtros.hasta" :min="filtros.desde || opciones?.fecha_min" :max="opciones?.fecha_max" />
      </label>
    </div>

    <label class="campo">Ciudad
      <select v-model="filtros.ciudad" @change="alCambiarCiudad">
        <option value="">Todas</option>
        <option v-for="c in opciones?.ciudades ?? []" :key="c.nombre" :value="c.nombre">{{ c.nombre }} ({{ c.n }})</option>
      </select>
    </label>
    <label class="campo">Calle o tramo
      <select v-model="filtros.tramo">
        <option value="">Todos</option>
        <option v-for="t in tramos" :key="t.nombre + t.ciudad" :value="t.nombre">{{ t.nombre }} ({{ t.n }})</option>
      </select>
    </label>

    <fieldset class="zonas">
      <legend>Zonas críticas</legend>
      <label class="chk"><input type="checkbox" v-model="filtros.zonas" /> Mostrar zonas con muchos baches</label>
      <template v-if="filtros.zonas">
        <label class="campo"><span>Cercanía: baches a menos de <b>{{ filtros.eps_m }} m</b> se consideran vecinos</span>
        <input type="range" min="5" max="200" step="5" v-model.number="filtros.eps_m" />
        </label>
        <label class="campo"><span>Densidad: cada bache necesita <b>{{ filtros.min_vecinos }}</b> baches cerca (contándose a sí mismo)</span>
        <input type="range" min="2" max="20" step="1" v-model.number="filtros.min_vecinos" />
        </label>
        <label class="campo"><span>Tamaño mínimo de la zona: <b>{{ filtros.min_baches }} baches</b></span>
        <input type="range" min="2" max="60" step="1" v-model.number="filtros.min_baches" />
        </label>
        <small class="suave">Parten de los valores guardados en Ajustes. Más densidad o más tamaño = menos zonas y más concentradas. Con densidad 2 los baches se encadenan y las zonas se alargan a toda la calle.</small>
      </template>
    </fieldset>

    <div class="acciones">
      <button class="boton sec" :disabled="!hayFiltros" @click="$emit('restablecer')">Restablecer</button>
      <button class="boton sec" @click="$emit('encuadrar')">Ver todos</button>
    </div>

    <div class="leyenda" aria-label="Leyenda">
      <span v-for="s in ORDEN_SEV" :key="s"><i :style="{ background: SEV[s].color, width: SEV[s].radio * 2 + 'px', height: SEV[s].radio * 2 + 'px' }"></i>{{ SEV[s].etiqueta }}</span>
      <span><i class="zona-ico"></i>Zona crítica</span>
    </div>
  </aside>
</template>

<style scoped>
.panel { position: absolute; z-index: 1000; background: var(--superficie); border: 1px solid var(--borde); border-radius: var(--radio);
  box-shadow: 0 6px 24px rgba(0, 0, 0, .22); overflow: auto; }
.panel-filtros { top: 12px; left: 12px; width: 292px; max-height: calc(100% - 24px); padding: .9rem 1rem 1rem; font-size: .88rem; }
header { display: flex; justify-content: space-between; align-items: center; }
h2 { font-size: 1.05rem; margin: 0; }
.cerrar { background: none; border: 0; font-size: 1.6rem; line-height: 1; color: var(--suave); cursor: pointer; padding: 0 .3rem; }
.cuenta { margin: .3rem 0 .6rem; color: var(--suave); }
.cuenta.cargando { opacity: .55; }
.cuenta b { color: var(--texto); font-size: 1.05rem; }
fieldset { border: 1px solid var(--borde); border-radius: 9px; margin: 0 0 .65rem; padding: .35rem .7rem .5rem; }
legend { padding: 0 .3rem; font-weight: 600; font-size: .8rem; color: var(--suave); }
.chk { display: flex; align-items: center; gap: .5rem; padding: .18rem 0; cursor: pointer; }
.punto { border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 0 1px var(--borde); display: inline-block; }
.campo { display: flex; flex-direction: column; gap: .2rem; margin-bottom: .6rem; color: var(--suave); font-size: .8rem; }
.campo b { color: var(--texto); }
.campo input, .campo select { font: inherit; padding: .35rem .45rem; border-radius: 7px; border: 1px solid var(--borde); background: var(--fondo); color: var(--texto); }
.campo input[type="range"] { padding: 0; accent-color: var(--marca); }
.fila { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; }
.zonas .campo { margin-top: .4rem; }
.acciones { display: flex; gap: .5rem; margin: .2rem 0 .7rem; }
.boton.sec { flex: 1; background: var(--fondo); color: var(--texto); border: 1px solid var(--borde); padding: .45rem; font-size: .85rem; }
.boton.sec:hover:not(:disabled) { background: var(--borde); }
.boton:disabled { opacity: .45; cursor: not-allowed; }
.leyenda { display: flex; flex-wrap: wrap; gap: .4rem .9rem; font-size: .78rem; color: var(--suave); }
.leyenda span { display: inline-flex; align-items: center; gap: .35rem; }
.leyenda i { border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 0 1px var(--borde); display: inline-block; box-sizing: content-box; }
.zona-ico { width: 14px !important; height: 14px !important; border-radius: 4px !important; background: rgba(124, 58, 237, .25); border: 2px dashed #7c3aed !important; box-shadow: none !important; }

@media (max-width: 760px) {
  .panel-filtros { top: auto; left: 8px; right: 8px; bottom: 8px; width: auto; max-height: 68%; }
}
</style>
