// Formas de avisar al conductor: voz, tono y vibración. Todo es opcional y se configura en los ajustes.
import { callar, hablar, vibrar } from "../plataforma/voz.js";
import { textoAviso } from "./motor.js";

export { vozDisponible } from "../plataforma/voz.js";

let ctx = null;

/** Hay que llamarla desde un gesto del usuario (pulsar «Iniciar»): los navegadores no dejan sonar antes. */
export function prepararAudio() {
  try {
    ctx ||= new (window.AudioContext || window.webkitAudioContext)();
    ctx.resume?.();
  } catch { /* sin audio */ }
  try { window.speechSynthesis?.getVoices(); } catch { /* sin voz */ }
}

function tono(frecuencia, inicio, duracion, volumen = 0.3) {
  if (!ctx) return;
  const o = ctx.createOscillator(), g = ctx.createGain(), t0 = ctx.currentTime + inicio;
  o.type = "sine";
  o.frequency.value = frecuencia;
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(volumen, t0 + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + duracion);
  o.connect(g).connect(ctx.destination);
  o.start(t0);
  o.stop(t0 + duracion + 0.05);
}

// Más severo = más agudo y más repetido (no depende solo del color de la pantalla).
const SONIDOS = {
  baja: () => tono(660, 0, 0.18),
  media: () => { tono(740, 0, 0.16); tono(740, 0.22, 0.16); },
  alta: () => { tono(880, 0, 0.14); tono(880, 0.2, 0.14); tono(1040, 0.4, 0.22); },
};
const VIBRACION = { baja: [120], media: [150, 90, 150], alta: [250, 100, 250, 100, 250] };


/** Emite un aviso según los ajustes y devuelve su texto. */
export function emitir(aviso, ajustes) {
  const texto = textoAviso(aviso);
  if (ajustes.sonido) { try { SONIDOS[aviso.sev]?.(); } catch { /* sin audio */ } }
  if (ajustes.vibracion) vibrar(VIBRACION[aviso.sev] || [150]);
  if (ajustes.voz) setTimeout(() => hablar(texto), ajustes.sonido ? 700 : 0);     // la voz entra después del tono
  return texto;
}

export function detenerVoz() {
  callar();
}
