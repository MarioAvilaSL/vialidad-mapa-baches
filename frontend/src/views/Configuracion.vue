<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { api } from "../api.js";
import { claveServidor, esNativo, guardarServidor, normalizarUrl, urlServidor } from "../plataforma/servidor.js";
import { borrarMosaicos, estadoMosaicos, fijarLimiteMosaicosMb, limiteMosaicosMb, LIMITES_MB } from "../plataforma/mosaicos.js";
import { cargarAjustesServidor, guardarAjustesServidor, restablecerAjustesServidor, servidor } from "../ajustesServidor.js";

const nativo = esNativo();
const conexion = reactive({ url: urlServidor(), clave: claveServidor() });
const prueba = ref(null);              // resultado de «Probar conexión»
const probando = ref(false);
const conexionGuardada = ref(false);

// Mapa guardado en el teléfono (solo en la app Android)
const mapaGuardado = reactive({ n: 0, bytes: 0, limite: limiteMosaicosMb() });
const mb = (b) => (b / 1048576).toFixed(b < 10485760 ? 1 : 0);
async function refrescarMapa() { Object.assign(mapaGuardado, await estadoMosaicos()); }
function cambiarLimite() { fijarLimiteMosaicosMb(mapaGuardado.limite); }
async function vaciarMapa() {
  if (confirm("¿Borrar el mapa guardado en este teléfono? Se volverá a guardar a medida que lo veas con conexión.")) { await borrarMosaicos(); await refrescarMapa(); }
}
if (nativo) refrescarMapa();

async function probarConexion() {
  probando.value = true; prueba.value = null; conexionGuardada.value = false;
  const base = nativo ? normalizarUrl(conexion.url) : "";
  if (nativo && !base) { prueba.value = { ok: false, texto: "Escribe la dirección del servidor, por ejemplo http://192.168.1.50:8001" }; probando.value = false; return; }
  try {
    const cab = conexion.clave.trim() ? { "X-Clave": conexion.clave.trim() } : {};
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 8000);
    const h = await fetch(`${base}/api/health`, { signal: ctl.signal }).then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); });
    const ac = await fetch(`${base}/api/acceso`, { headers: cab, signal: ctl.signal }).then((r) => r.json());
    clearTimeout(t);
    const partes = [`Conectado. Base de datos ${h.db ? "✓" : "✗"}, PostGIS ${h.postgis ? "✓" : "✗"}, motor de rutas ${h.rutas?.disponible ? "✓" : "no disponible"}.`];
    let ok = !!h.db;
    if (ac.requiere_clave) {
      partes.push(ac.clave_valida ? "La clave es correcta." : conexion.clave.trim() ? "La clave es incorrecta." : "El servidor pide una clave para importar y cambiar ajustes.");
      if (!ac.clave_valida) ok = false;
    } else if (conexion.clave.trim()) {
      partes.push("El servidor no pide clave (puedes dejarla vacía).");
    }
    prueba.value = { ok, texto: partes.join(" ") };
  } catch (e) {
    prueba.value = { ok: false, texto: nativo
      ? "No se pudo conectar. Comprueba que el backend esté en marcha con --host 0.0.0.0, que el celular y la PC estén en la misma red Wi-Fi y que el firewall de Windows permita el puerto 8001 (ver README)."
      : "No se pudo conectar con el servidor." };
  } finally {
    probando.value = false;
  }
}
async function guardarConexion() {
  guardarServidor(nativo ? conexion.url : urlServidor(), conexion.clave);
  conexion.url = urlServidor();
  conexionGuardada.value = true;
  await cargarAjustesServidor(true);
  copiar();
  previsualizar();
}

const form = reactive({ ...servidor.valores });
const guardando = ref(false);
const mensaje = ref("");
const error = ref("");
const vista = ref(null);              // vista previa de zonas con los valores del formulario
const cargandoVista = ref(false);
const salud = ref(null);
const resumen = ref(null);
let temporizador = null, ticket = 0;

const cambiado = computed(() => Object.keys(form).some((k) => form[k] !== servidor.valores[k]));
const esDeFabrica = computed(() => Object.keys(form).every((k) => form[k] === servidor.defectos[k]));

function copiar() { Object.assign(form, servidor.valores); }

async function previsualizar() {
  const mi = ++ticket;
  cargandoVista.value = true;
  try {
    const q = new URLSearchParams({ eps_m: form.eps_m, min_vecinos: form.min_vecinos, min_baches: form.min_baches });
    const z = await api(`/zonas?${q}`);
    if (mi !== ticket) return;
    const tam = z.features.map((f) => f.properties.n);
    vista.value = { zonas: tam.length, mayor: tam[0] ?? 0, enZonas: tam.reduce((a, b) => a + b, 0) };
  } catch {
    if (mi === ticket) vista.value = null;
  } finally {
    if (mi === ticket) cargandoVista.value = false;
  }
}

async function guardar() {
  guardando.value = true; error.value = ""; mensaje.value = "";
  try {
    await guardarAjustesServidor({ ...form });
    mensaje.value = "Guardado. El mapa, la conducción y el planificador usarán estos valores.";
  } catch (e) {
    error.value = e.detalle || e.message;
  } finally {
    guardando.value = false;
  }
}
async function restablecer() {
  guardando.value = true; error.value = ""; mensaje.value = "";
  try {
    await restablecerAjustesServidor();
    copiar();
    mensaje.value = "Se restablecieron los valores de fábrica.";
  } catch (e) {
    error.value = e.detalle || e.message;
  } finally {
    guardando.value = false;
  }
}

onMounted(async () => {
  await cargarAjustesServidor(true);
  if (servidor.error) error.value = `No se pudieron cargar los ajustes guardados: ${servidor.error}`;
  copiar();
  previsualizar();
  watch(() => [form.eps_m, form.min_vecinos, form.min_baches], () => { clearTimeout(temporizador); temporizador = setTimeout(previsualizar, 300); });
  try { [salud.value, resumen.value] = await Promise.all([api("/health"), api("/resumen")]); } catch { /* el panel de sistema queda vacío */ }
});

const fecha = (iso) => (iso ? new Date(iso).toLocaleString("es-EC", { timeZone: "America/Guayaquil" }) : "Nunca");
</script>

<template>
  <section class="vista">
    <h1>Ajustes</h1>

    <div class="tarjeta" :class="{ destacada: nativo && !urlServidor() }">
      <h2 style="margin-top:0">Conexión con el servidor</h2>
      <template v-if="nativo">
        <p class="suave" style="margin-top:0">Escribe la dirección de la PC donde corre el backend, con su puerto (por ejemplo <b>http://192.168.1.50:8001</b>).
          El celular y la PC deben estar en la misma red Wi-Fi. Una vez cargados los baches, el modo de conducción funciona también sin conexión.</p>
        <label class="campo"><span>Dirección del servidor</span>
          <input v-model="conexion.url" inputmode="url" autocapitalize="off" autocomplete="off" placeholder="http://192.168.1.50:8001" /></label>
      </template>
      <p v-else class="suave" style="margin-top:0">En el navegador de la PC la dirección no hace falta. Si definiste <code>API_TOKEN</code> en <code>backend\.env</code>, escribe aquí la clave.</p>
      <label class="campo"><span>Clave de acceso <small>(opcional; solo si el servidor tiene <code>API_TOKEN</code>)</small></span>
        <input v-model="conexion.clave" type="password" autocomplete="off" /></label>
      <div class="barra" style="margin:0">
        <button class="boton sec" :disabled="probando" @click="probarConexion">{{ probando ? "Probando…" : "Probar conexión" }}</button>
        <button class="boton" @click="guardarConexion">Guardar conexión</button>
      </div>
      <p v-if="prueba" :class="prueba.ok ? 'ok' : 'error'" role="status">{{ prueba.texto }}</p>
      <p v-if="conexionGuardada" class="ok">Conexión guardada.</p>
    </div>

    <div v-if="nativo" class="tarjeta">
      <h2 style="margin-top:0">Mapa guardado en el teléfono</h2>
      <p class="suave">Los cuadros del mapa que ves con conexión se guardan para verlos después sin conexión. Solo se guarda lo que ya miraste:
        para tener lista una zona, recórrela antes en el mapa con Wi-Fi o datos.</p>
      <p>Guardado ahora: <b>{{ mb(mapaGuardado.bytes) }} MB</b> ({{ mapaGuardado.n }} cuadros).</p>
      <label class="campo">Espacio máximo
        <select v-model.number="mapaGuardado.limite" @change="cambiarLimite">
          <option v-for="m in LIMITES_MB" :key="m" :value="m">{{ m === 0 ? "No guardar" : m + " MB" }}</option>
        </select>
        <small>Al llegar al máximo se borran primero los cuadros más antiguos. El cambio se aplica al abrir de nuevo cada mapa.</small>
      </label>
      <div class="barra" style="margin:0">
        <button class="boton sec" @click="refrescarMapa">Actualizar</button>
        <button class="boton sec" @click="vaciarMapa">Borrar mapa guardado</button>
      </div>
    </div>

    <div class="tarjeta">
      <h2 style="margin-top:0">Zonas críticas</h2>
      <p class="suave">Una zona crítica es una concentración real de baches. Estos valores se guardan en el servidor y son los que usan por defecto el mapa,
        la conducción y el planificador de rutas, tanto en la web como en Android.</p>
      <label class="campo"><span>Cercanía: baches a menos de <b>{{ form.eps_m }} m</b> se consideran vecinos</span>
        <input type="range" min="5" max="200" step="5" v-model.number="form.eps_m" />
      </label>
      <label class="campo"><span>Densidad: cada bache necesita <b>{{ form.min_vecinos }}</b> baches cerca (contándose a sí mismo)</span>
        <input type="range" min="2" max="20" step="1" v-model.number="form.min_vecinos" />
      </label>
      <label class="campo"><span>Tamaño mínimo de una zona: <b>{{ form.min_baches }} baches</b></span>
        <input type="range" min="2" max="60" step="1" v-model.number="form.min_baches" />
      </label>
      <p class="vista-previa" :class="{ cargando: cargandoVista }">
        <template v-if="vista">Con estos valores: <b>{{ vista.zonas }} zona{{ vista.zonas === 1 ? "" : "s" }}</b>
          <template v-if="vista.zonas"> (la mayor, de {{ vista.mayor }} baches; {{ vista.enZonas }} baches dentro de zonas<template v-if="resumen"> de {{ resumen.baches_activos }}</template>)</template>.</template>
        <template v-else>Calculando…</template>
      </p>
      <p class="suave nota">Si salen demasiadas zonas o una gigante, sube la densidad o el tamaño mínimo; si no sale ninguna, bájalos. Densidad 2 encadena los baches y las zonas se alargan por toda la calle.</p>
    </div>

    <div class="tarjeta">
      <h2 style="margin-top:0">Rutas</h2>
      <label class="campo"><span>Ancho del corredor: se cuentan los baches a menos de <b>{{ form.ancho_m }} m</b> del eje de la ruta</span>
        <input type="range" min="5" max="100" step="5" v-model.number="form.ancho_m" />
      </label>
      <p class="suave nota">La ubicación de cada bache es la de la cámara, con unos metros de error: un corredor muy estrecho puede dejar fuera baches de tu carril; uno muy ancho incluye los de calles paralelas.</p>
    </div>

    <div class="barra">
      <button class="boton" :disabled="!cambiado || guardando" @click="guardar">{{ guardando ? "Guardando…" : "Guardar" }}</button>
      <button class="boton sec" :disabled="!cambiado || guardando" @click="copiar">Descartar cambios</button>
      <button class="boton sec" :disabled="(esDeFabrica && !cambiado && !servidor.actualizado_en) || guardando" @click="restablecer">Valores de fábrica</button>
      <span v-if="servidor.actualizado_en && !mensaje" class="suave"><small>Guardado el {{ fecha(servidor.actualizado_en) }}</small></span>
    </div>
    <p v-if="mensaje" class="ok" role="status">{{ mensaje }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div class="tarjeta">
      <h2 style="margin-top:0">Alertas de conducción</h2>
      <p class="suave" style="margin-top:0">La distancia de aviso, la severidad mínima, la voz, el tono y la vibración se configuran en cada dispositivo.</p>
      <router-link class="boton enlace-b" to="/alertas">Abrir ajustes de alertas</router-link>
    </div>

    <div class="tarjeta">
      <h2 style="margin-top:0">Datos y sistema</h2>
      <p style="margin-top:0">Última importación: <b>{{ resumen ? fecha(resumen.ultima_importacion) : "—" }}</b>
        · {{ resumen ? resumen.baches_activos : "—" }} baches activos.
        <router-link to="/actualizacion">Actualizar mapas de registros</router-link></p>
      <ul v-if="salud" class="estados">
        <li :class="salud.api ? 'ok' : 'mal'"><i></i>Servidor</li>
        <li :class="salud.db ? 'ok' : 'mal'"><i></i>Base de datos</li>
        <li :class="salud.postgis ? 'ok' : 'mal'"><i></i>PostGIS <small v-if="salud.postgis">{{ salud.postgis.split(" ")[0] }}</small></li>
        <li :class="salud.origen.alcanzable ? 'ok' : salud.origen.configurado ? 'mal' : 'neutro'"><i></i>Proyecto original (solo lectura)
          <small v-if="!salud.origen.alcanzable"> · {{ salud.origen.detalle }}</small></li>
        <li :class="salud.rutas?.disponible ? 'ok' : 'neutro'"><i></i>Motor de rutas <small v-if="!salud.rutas?.disponible"> · opcional (ver graphhopper/README.md)</small></li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.vista > .tarjeta { margin-bottom: 1rem; max-width: 760px; }
.campo { display: flex; flex-direction: column; gap: .25rem; color: var(--suave); font-size: .92rem; margin-bottom: .8rem; }
.campo b { color: var(--texto); }
.campo input[type="range"] { accent-color: var(--marca); }
.vista-previa { margin: .4rem 0; padding: .5rem .8rem; background: var(--fondo); border-radius: 8px; }
.vista-previa.cargando { opacity: .55; }
.nota { font-size: .82rem; margin: .5rem 0 0; }
.barra { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; margin: 0 0 .8rem; }
.boton.sec { background: var(--fondo); color: var(--texto); border: 1px solid var(--borde); }
.boton:disabled { opacity: .45; cursor: not-allowed; }
.enlace-b { display: inline-block; text-decoration: none; }
.campo input { font: inherit; padding: .45rem .55rem; border-radius: 8px; border: 1px solid var(--borde); background: var(--fondo); color: var(--texto); }
.destacada { border-color: var(--marca); box-shadow: 0 0 0 2px color-mix(in srgb, var(--marca) 30%, transparent); }
.ok { color: var(--ok); }
.error { color: var(--mal); }
</style>
