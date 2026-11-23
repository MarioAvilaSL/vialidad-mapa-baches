<script setup>
import { ajustes, DEFECTO } from "../conduccion/ajustes.js";
import { vozDisponible } from "../conduccion/avisos.js";
</script>

<template>
  <div class="ajustes">
    <label class="campo"><span>Distancia de aviso de un bache: <b>{{ ajustes.radio_m }} m</b></span>
        <input type="range" min="50" max="500" step="10" v-model.number="ajustes.radio_m" />
      <small>Es la distancia mínima. A más velocidad el aviso se adelanta solo (unos 6 segundos antes).</small>
    </label>
    <label class="campo">Avisar baches de severidad
      <select v-model="ajustes.nivel_min">
        <option value="baja">Todas (baja, media y alta)</option>
        <option value="media">Media y alta</option>
        <option value="alta">Solo alta</option>
      </select>
    </label>
    <label class="chk"><input type="checkbox" v-model="ajustes.zonas" /> Avisar zonas críticas (y no baches uno por uno dentro de ellas)</label>
    <label class="chk"><input type="checkbox" v-model="ajustes.voz" :disabled="!vozDisponible()" /> Voz
      <small v-if="!vozDisponible()">(este navegador no la ofrece)</small></label>
    <label class="chk"><input type="checkbox" v-model="ajustes.sonido" /> Tono</label>
    <label class="chk"><input type="checkbox" v-model="ajustes.vibracion" /> Vibración <small>(solo celulares)</small></label>
    <label class="chk"><input type="checkbox" v-model="ajustes.mapa" /> Mostrar el mapa en modo conducción</label>
    <button class="boton sec" @click="Object.assign(ajustes, DEFECTO)">Restablecer valores</button>
  </div>
</template>

<style scoped>
.ajustes { display: grid; gap: .7rem; }
.campo { display: flex; flex-direction: column; gap: .25rem; color: var(--suave); font-size: .9rem; }
.campo b { color: var(--texto); }
.campo select { font: inherit; padding: .4rem .5rem; border-radius: 8px; border: 1px solid var(--borde); background: var(--fondo); color: var(--texto); }
.campo input[type="range"] { accent-color: var(--marca); }
.chk { display: flex; align-items: center; gap: .5rem; cursor: pointer; }
.boton.sec { justify-self: start; background: var(--fondo); color: var(--texto); border: 1px solid var(--borde); }
</style>
