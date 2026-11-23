<script setup>
import { onMounted, ref } from "vue";
import { api } from "../api.js";

const salud = ref(null);
const resumen = ref(null);
const error = ref("");

async function cargar() {
  error.value = "";
  try {
    [salud.value, resumen.value] = await Promise.all([api("/health"), api("/resumen")]);
  } catch (e) {
    salud.value = null;
    error.value = "No se pudo contactar con el servidor. ¿Está en marcha el backend (puerto 8001)?";
  }
}
onMounted(cargar);

const fecha = (iso) => (iso ? new Date(iso).toLocaleString("es-EC") : "Aún no se ha importado nada");
</script>

<template>
  <section class="vista">
    <h1>Inicio</h1>

    <div v-if="error" class="tarjeta aviso">
      <p>{{ error }}</p>
      <button class="boton" @click="cargar">Reintentar</button>
    </div>

    <template v-else-if="salud">
      <div class="cuadricula">
        <div class="tarjeta cifra"><small>Baches en el mapa</small><strong>{{ resumen?.baches_activos ?? 0 }}</strong></div>
        <div class="tarjeta cifra"><small>Última importación</small><span class="fecha">{{ fecha(resumen?.ultima_importacion) }}</span></div>
        <div class="tarjeta cifra">
          <small>Por severidad (heurística)</small>
          <span class="sev"><b class="alta">{{ resumen?.por_severidad?.alta ?? 0 }}</b> alta ·
            <b class="media">{{ resumen?.por_severidad?.media ?? 0 }}</b> media ·
            <b class="baja">{{ resumen?.por_severidad?.baja ?? 0 }}</b> baja</span>
        </div>
        <div class="tarjeta cifra">
          <small>Origen · evidencia</small>
          <span class="sev">{{ resumen?.por_origen?.foto ?? 0 }} fotos · {{ resumen?.por_origen?.video ?? 0 }} videos<br />{{ resumen?.con_evidencia ?? 0 }} con imagen</span>
        </div>
      </div>

      <h2>Estado de los componentes</h2>
      <ul class="estados">
        <li :class="salud.api ? 'ok' : 'mal'"><i></i>Servidor (API)</li>
        <li :class="salud.db ? 'ok' : 'mal'"><i></i>Base de datos propia</li>
        <li :class="salud.postgis ? 'ok' : 'mal'"><i></i>PostGIS<small v-if="salud.postgis"> {{ salud.postgis.split(' ')[0] }}</small></li>
        <li v-if="salud.rutas" :class="salud.rutas.disponible ? 'ok' : 'neutro'">
          <i></i>Motor de rutas (GraphHopper)
          <small v-if="!salud.rutas.disponible"> · opcional, solo para el planificador de rutas (ver graphhopper/README.md)</small>
        </li>
        <li :class="salud.origen.alcanzable ? 'ok' : salud.origen.configurado ? 'mal' : 'neutro'">
          <i></i>Proyecto original (solo lectura)
          <small v-if="!salud.origen.configurado"> · sin configurar (ver README, paso 4)</small>
          <small v-else-if="!salud.origen.alcanzable"> · {{ salud.origen.detalle }}</small>
        </li>
      </ul>
    </template>

    <p v-else class="suave">Cargando…</p>
  </section>
</template>

<style scoped>
.sev { font-size: 1rem; font-weight: 600; margin-top: .35rem; line-height: 1.5; }
.sev b { font-size: 1.3rem; }
.alta { color: #b91c1c; }
.media { color: #b45309; }
.baja { color: #15803d; }
</style>
