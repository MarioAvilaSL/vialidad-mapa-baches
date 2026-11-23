import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// El backend corre en el puerto 8001 (el proyecto original usa el 8000, así pueden funcionar a la vez).
const BACKEND = process.env.VITE_BACKEND || "http://127.0.0.1:8001";

export default defineConfig({
  plugins: [vue()],
  server: {
    host: "0.0.0.0", // permite abrirlo desde el celular en la misma red durante el desarrollo
    port: 5173,
    proxy: {
      "/api": BACKEND,
      "/media": BACKEND,
    },
  },
});
