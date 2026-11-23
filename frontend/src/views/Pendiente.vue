<script setup>
import { useRoute } from "vue-router";
const ruta = useRoute();
</script>

<template>
  <section class="vista">
    <h1>{{ ruta.meta.etiqueta }}</h1>
    <div class="tarjeta pendiente">
      <span class="insignia">Fase {{ ruta.meta.fase }}</span>
      <p>{{ ruta.meta.descripcion }}</p>
      <p class="suave">Esta sección ya está en el menú, pero se construirá en su fase.</p>
    </div>
  </section>
</template>
