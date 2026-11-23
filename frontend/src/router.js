import { createRouter, createWebHashHistory } from "vue-router";
import Inicio from "./views/Inicio.vue";
import Actualizacion from "./views/Actualizacion.vue";
import Mapa from "./views/Mapa.vue";
import Conduccion from "./views/Conduccion.vue";
import Alertas from "./views/Alertas.vue";
import Estadisticas from "./views/Estadisticas.vue";
import Configuracion from "./views/Configuracion.vue";
import { esNativo, urlServidor } from "./plataforma/servidor.js";
import Pendiente from "./views/Pendiente.vue";

// Hash history: funciona igual en el navegador, en Capacitor (Android) y sin configurar el servidor.
export const secciones = [
  { path: "/", name: "inicio", etiqueta: "Inicio", icono: "◧", component: Inicio },
  { path: "/mapa", name: "mapa", etiqueta: "Mapa", icono: "◉", component: Mapa, ancho: true },
  { path: "/conduccion", name: "conduccion", etiqueta: "Conducción", icono: "➤", component: Conduccion, ancho: true },
  { path: "/alertas", name: "alertas", etiqueta: "Alertas", icono: "◬", component: Alertas },
  { path: "/estadisticas", name: "estadisticas", etiqueta: "Estadísticas", icono: "▥", component: Estadisticas },
  { path: "/configuracion", name: "configuracion", etiqueta: "Ajustes", icono: "⚙", component: Configuracion },
  { path: "/actualizacion", name: "actualizacion", etiqueta: "Actualizar", icono: "↻", component: Actualizacion },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes: secciones.map((s) => ({
    path: s.path, name: s.name,
    component: s.component || Pendiente,
    meta: { etiqueta: s.etiqueta, fase: s.fase, descripcion: s.descripcion, ancho: !!s.ancho },
  })),
});

// En la app Android, hasta indicar dónde está el servidor solo se puede abrir Ajustes
router.beforeEach((to) => {
  if (esNativo() && !urlServidor() && to.name !== "configuracion") return { name: "configuracion" };
});

export default router;
