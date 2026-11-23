<script setup>
import { computed } from "vue";
import AjustesAlertas from "../components/AjustesAlertas.vue";
import { historial, borrarHistorial } from "../conduccion/historial.js";
import { SEV } from "../mapa/utilidades.js";

const items = computed(() => historial.items);
const hora = (t) => new Date(t).toLocaleString("es-EC", { timeZone: "America/Guayaquil", dateStyle: "short", timeStyle: "medium" });
</script>

<template>
  <section class="vista">
    <h1>Alertas</h1>
    <div class="cols">
      <div class="tarjeta">
        <h2 style="margin-top:0">Configuración</h2>
        <AjustesAlertas />
        <p class="suave" style="margin-bottom:0"><small>Se guardan en este dispositivo y se aplican en el modo de conducción.</small></p>
      </div>
      <div class="tarjeta">
        <div class="cab">
          <h2 style="margin:0">Historial</h2>
          <button v-if="items.length" class="boton sec" @click="borrarHistorial">Borrar</button>
        </div>
        <p v-if="!items.length" class="suave">Todavía no hay avisos. Aparecerán aquí los que se emitan en el modo de conducción.</p>
        <ul v-else class="lista">
          <li v-for="(a, i) in items" :key="a.t + '-' + i">
            <i class="p" :class="a.tipo" :style="a.tipo === 'bache' ? { background: SEV[a.sev]?.color } : null"></i>
            <div>
              <span>{{ a.texto }}<span v-if="a.simulado" class="sim">simulado</span></span><br />
              <small class="suave">{{ hora(a.t) }}<template v-if="a.tramo || a.ciudad"> · {{ [a.tramo, a.ciudad].filter(Boolean).join(", ") }}</template></small>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>

<style scoped>
.cols { display: grid; grid-template-columns: minmax(280px, 1fr) minmax(320px, 1.3fr); gap: 1rem; align-items: start; }
.cab { display: flex; justify-content: space-between; align-items: center; margin-bottom: .6rem; }
.lista { list-style: none; margin: 0; padding: 0; max-height: 60vh; overflow: auto; display: grid; gap: .55rem; }
.lista li { display: flex; gap: .7rem; align-items: flex-start; }
.p { flex: none; width: 12px; height: 12px; border-radius: 50%; margin-top: .4rem; }
.p.zona { border-radius: 3px; background: #7c3aed; }
.sim { margin-left: .5rem; font-size: .7rem; border: 1px solid var(--borde); border-radius: 99px; padding: 0 .4rem; color: var(--suave); }
.boton.sec { background: var(--fondo); color: var(--texto); border: 1px solid var(--borde); padding: .3rem .8rem; }
@media (max-width: 760px) { .cols { grid-template-columns: 1fr; } }
</style>
