// Añade permisos y ajustes necesarios al proyecto Android generado por Capacitor.
// Es idempotente: se puede ejecutar varias veces sin duplicar nada.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const raiz = join(dirname(fileURLToPath(import.meta.url)), "..");
const ruta = join(raiz, "android", "app", "src", "main", "AndroidManifest.xml");
if (!existsSync(ruta)) {
  console.error("No existe android/. Ejecuta primero: npx cap add android");
  process.exit(1);
}

const permisos = [
  "INTERNET",
  "ACCESS_NETWORK_STATE",
  "ACCESS_FINE_LOCATION",
  "ACCESS_COARSE_LOCATION",
  "FOREGROUND_SERVICE",
  "FOREGROUND_SERVICE_LOCATION",
  "POST_NOTIFICATIONS",
  "VIBRATE",
  "WAKE_LOCK",
];

let xml = readFileSync(ruta, "utf8");
const original = xml;

const faltan = permisos.filter((p) => !xml.includes(`android.permission.${p}"`));
if (faltan.length) {
  const bloque = faltan
    .map((p) => `    <uses-permission android:name="android.permission.${p}" />`)
    .join("\n");
  xml = xml.replace(/<\/application>/, `</application>\n\n${bloque}`);
}

if (!xml.includes("usesCleartextTraffic")) {
  xml = xml.replace(/<application\b/, '<application\n        android:usesCleartextTraffic="true"');
}

if (xml !== original) {
  writeFileSync(ruta, xml);
  console.log(`Manifest actualizado (${faltan.length} permisos añadidos).`);
} else {
  console.log("Manifest ya estaba preparado.");
}
