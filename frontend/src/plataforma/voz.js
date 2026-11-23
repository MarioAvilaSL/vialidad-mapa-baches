// Voz, vibración y pantalla encendida. En la app Android se usan los plugins nativos (más fiables que las funciones
// del navegador); en el navegador, las del navegador. Todo es opcional: si algo falla, se sigue sin ello.
import { esNativo } from "./servidor.js";

export async function hablar(texto) {
  if (esNativo()) {
    try {
      const { TextToSpeech } = await import("@capacitor-community/text-to-speech");
      await TextToSpeech.speak({ text: texto, lang: "es-ES", rate: 1.05, pitch: 1.0, volume: 1.0, category: "ambient", queueStrategy: 0 });
      return;
    } catch { /* se prueba con la del navegador */ }
  }
  const s = typeof window !== "undefined" ? window.speechSynthesis : null;
  if (!s) return;
  try {
    s.cancel();
    const u = new SpeechSynthesisUtterance(texto);
    const voz = s.getVoices().find((v) => /^es[-_]/i.test(v.lang) && /EC|MX|US|419/i.test(v.lang)) || s.getVoices().find((v) => /^es/i.test(v.lang));
    if (voz) u.voice = voz;
    u.lang = voz?.lang || "es-ES";
    u.rate = 1.05;
    s.speak(u);
  } catch { /* sin voz */ }
}

export async function callar() {
  if (esNativo()) {
    try { const { TextToSpeech } = await import("@capacitor-community/text-to-speech"); await TextToSpeech.stop(); } catch { /* nada */ }
  }
  try { window.speechSynthesis?.cancel(); } catch { /* nada */ }
}

export const vozDisponible = () => esNativo() || (typeof window !== "undefined" && "speechSynthesis" in window);

export async function vibrar(patron) {
  if (esNativo()) {
    try {
      const { Haptics } = await import("@capacitor/haptics");
      // el plugin vibra una duración; se emula el patrón (vibra, pausa, vibra…)
      for (let i = 0; i < patron.length; i += 2) {
        await Haptics.vibrate({ duration: patron[i] });
        if (patron[i + 1]) await new Promise((r) => setTimeout(r, patron[i + 1]));
      }
      return;
    } catch { /* se prueba con la del navegador */ }
  }
  try { navigator.vibrate?.(patron); } catch { /* sin vibración */ }
}

let pantalla = null;
/** Mantiene la pantalla encendida mientras se conduce. Devuelve una función que lo libera. */
export async function mantenerPantalla() {
  if (esNativo()) {
    try {
      const { KeepAwake } = await import("@capacitor-community/keep-awake");
      await KeepAwake.keepAwake();
      return () => { KeepAwake.allowSleep().catch(() => {}); };
    } catch { return () => {}; }
  }
  try {
    pantalla = await navigator.wakeLock?.request("screen");
    return () => { try { pantalla?.release(); } catch { /* nada */ } pantalla = null; };
  } catch { return () => {}; }
}
