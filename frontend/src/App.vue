<script setup>
import { useRoute } from "vue-router";
import { secciones } from "./router.js";

const ruta = useRoute();
</script>

<template>
  <div class="app">
    <aside class="nav">
      <div class="marca"><span class="logo">◈</span><span class="marca-txt">Vialidad<b>Mapa</b></span></div>
      <nav>
        <RouterLink v-for="s in secciones" :key="s.name" :to="s.path" class="enlace">
          <span class="ico" aria-hidden="true">{{ s.icono }}</span>
          <span class="etq">{{ s.etiqueta }}</span>
        </RouterLink>
      </nav>
    </aside>
    <main class="contenido" :class="{ ancho: ruta.meta.ancho }">
      <RouterView />
    </main>
  </div>
</template>
