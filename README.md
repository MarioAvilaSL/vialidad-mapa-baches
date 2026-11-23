# Vialidad Mapa · Baches

Plataforma web y Android para consultar en un mapa los baches detectados por el proyecto
**Vialidad · YOLO26** y recibir avisos de zonas con baches mientras se conduce.

> **Estado: Fase 7 de 8 (app Android).** Ya funcionan la importación desde el proyecto original, el mapa con
> zonas críticas, el modo de conducción con alertas, el planificador de rutas A → B, las estadísticas y los ajustes
> compartidos. La app Android (Capacitor) está lista para probar en un teléfono; las pruebas finales y la documentación completa son la Fase 8.

Este proyecto es **independiente** del original: tiene su propia base de datos y solo *lee* del original, con un
usuario de solo lectura, cuando el usuario pulse «Actualizar mapas de registros» (Fase 3).

## Estructura

```
vialidad-mapa/
  backend/      API (FastAPI + SQLAlchemy + GeoAlchemy2)
    app/        código de la aplicación
    scripts/    crear_bd.py: prepara la base de datos
    tests/      pruebas automáticas
    storage/    evidencias copiadas del original (no se versiona)
  frontend/     interfaz (Vue 3 + Vite)
  graphhopper/  motor de rutas (GraphHopper): configuración, arranque en Windows y README
  sql/          origen_usuario_lectura.sql: usuario de solo lectura para el proyecto original
```

## Requisitos (Windows)

- Python 3.11 a 3.13
- Node.js 22 o superior (versión LTS, desde nodejs.org; con 20 funciona la web pero no la app Android)
- PostgreSQL 16 **con PostGIS** (ver el paso 1)

## Instalación

### 1. Instalar PostGIS (una sola vez)

1. Abre **Application Stack Builder** (menú Inicio, carpeta *PostgreSQL 16*).
2. Elige tu servidor PostgreSQL 16 y pulsa *Next*.
3. Abre **Spatial Extensions** y marca **PostGIS 3.x Bundle for PostgreSQL 16**.
4. Instálalo con las opciones por defecto. Si pregunta por crear una base de datos de ejemplo o registrar
   variables GDAL, puedes decir que **no**.

### 2. Backend

En PowerShell, dentro de la carpeta `backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # si se bloquea: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt

copy .env.example .env            # abre .env y escribe tu contraseña de PostgreSQL en DATABASE_URL

python -m scripts.crear_bd        # crea la base «baches_mapa», activa PostGIS y crea las tablas
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

El backend usa el puerto **8001** para no chocar con el proyecto original (puerto 8000).
Documentación interactiva de la API: <http://127.0.0.1:8001/docs>.

`python -m scripts.crear_bd` se puede repetir sin riesgo: no borra nada. Si PostGIS falta, te lo dice y te
indica qué instalar.

### 3. Frontend

En otra ventana de PowerShell, dentro de la carpeta `frontend`:

```powershell
npm install
npm run dev
```

Abre <http://localhost:5173>. En **Inicio** debes ver cuatro indicadores de estado. Los tres primeros (servidor,
base de datos y PostGIS) deben estar en verde. El cuarto («Proyecto original») aparecerá en gris hasta que
configures el paso 4.

### 4. Conexión de solo lectura al proyecto original (opcional por ahora)

1. En pgAdmin, conéctate a la base `vialidad` (la del proyecto original) como usuario `postgres`.
2. Abre `sql/origen_usuario_lectura.sql`, cambia la contraseña, pégalo en el Query Tool y pulsa F5.
3. En `backend/.env` completa `ORIGEN_DATABASE_URL` con la línea que indica el final de ese archivo.
4. Reinicia el backend. El indicador «Proyecto original» pasará a verde.

El usuario creado solo puede **leer** cinco tablas; no puede modificar ni borrar nada del proyecto original.

## Actualizar mapas de registros (Fase 3)

Si vienes de la Fase 2, en `backend` (con `(.venv)` activo) instala la dependencia nueva y reinicia el backend:

```powershell
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Al arrancar, el backend añade solo las columnas nuevas de la base de datos; no pierdes nada.

En `backend\.env` indica también la carpeta `storage` del proyecto original, para que se copien las imágenes de evidencia
(sin comillas, con la ruta completa):

```
ORIGEN_STORAGE_DIR=C:\ruta\a\tu\proyecto-original\storage
```

Después abre la sección **Actualizar** y pulsa **Actualizar mapas de registros**. Cada bache del original cae en una
sola categoría:

| Categoría | Significado |
|---|---|
| Nuevos | Se importaron por primera vez |
| Actualizados | Ya estaban, pero algo cambió en el original (o se les añadió la imagen que faltaba) |
| Duplicados | Ya estaban importados y sin cambios: no se vuelven a crear |
| Descartados en el original | Los marcaste con la ✕ en el proyecto original: no se muestran |
| Sin GPS válido | No tienen coordenadas utilizables, no se pueden ubicar en el mapa |
| Errores | Fallo inesperado con ese registro; los demás se importan igual |

Además, lo que se importó antes y ya no existe en el original se conserva marcado como «retirado» (no se borra).

**Qué se importa:** solo la clase `pothole`, de fotos (`detecciones`) y videos (`video_hallazgos`). En fotos, la
evidencia es un recorte alrededor del bache con su caja dibujada; en videos, la imagen del hallazgo.

**Límites que conviene conocer**
- La ubicación es la de la cámara/teléfono, no la del bache (puede haber unos metros de diferencia).
- Varios baches de una misma foto comparten las mismas coordenadas.
- La **severidad** (baja/media/alta) es una heurística propia a partir del tamaño relativo, la confianza y, en video,
  la persistencia. No es una medición de ingeniería vial. Sus pesos y umbrales están en `app/severidad.py`.
- El **rumbo** (sentido de marcha) solo se calcula para baches de video con ruta GPX.

Para revisar lo importado desde pgAdmin (base `baches_mapa`):

```sql
SELECT origen_tipo, severidad_nivel, count(*) FROM baches WHERE estado = 'activo' GROUP BY 1, 2 ORDER BY 1, 2;
```

## Mapa de baches (Fase 4)

Si vienes de la Fase 3, en la carpeta `frontend` instala las dos librerías nuevas (Leaflet y su agrupador) y reinicia
`npm run dev`. En el backend no hay dependencias nuevas; basta con reiniciarlo.

```powershell
cd frontend
npm install
npm run dev
```

En **Mapa** verás:

- **Marcadores** de cada bache, con color y tamaño según su severidad estimada (alta, media, baja). Cuando hay muchos
  juntos se **agrupan** en un círculo con el número de baches; su color es el del bache más severo que contiene.
  Al acercarte se separan. Pulsa un círculo para acercarte.
- **Detalle:** al pulsar un bache se abre un panel con la imagen de evidencia, fecha y hora, confianza, coordenadas
  (con botón para copiarlas), calle o tramo, origen (foto o video), fuente del GPS y, en videos, el sentido de marcha.
- **Filtros** (panel de la izquierda; en el celular, el botón «Filtros»): severidad, origen, confianza mínima,
  rango de fechas, ciudad y calle o tramo. El contador indica cuántos baches cumplen.
- **Zonas críticas** (en violeta): concentraciones reales de baches (agrupación por densidad, DBSCAN en PostGIS).
  Un bache es «denso» si tiene a su alrededor, a menos de la *cercanía* indicada, al menos la *densidad* indicada de
  baches (contándose a sí mismo); las zonas son los baches densos conectados y deben tener un *tamaño mínimo*.
  Pulsa una zona para ver sus baches, la mezcla de severidades, la calle y en cuántos registros (fotos o videos)
  distintos se ven. La insignia con el número aparece al acercarse. Las zonas respetan los filtros activos.

**Mosaicos del mapa.** Por defecto usa los de OpenStreetMap, gratuitos y adecuados para un uso moderado (sus condiciones
de uso limitan el uso intensivo). Necesita conexión a internet. Para usar otro servidor, crea `frontend/.env` con
`VITE_TILES_URL=https://tu-servidor/{z}/{x}/{y}.png`.

**Valores por defecto sin calibrar.** 30 m de cercanía, densidad 6 y tamaño mínimo 8 son un punto de partida, no un
valor validado. Si ves demasiadas zonas o una zona gigante, sube la densidad o el tamaño mínimo; si no ves ninguna,
bájalos. Densidad 2 equivale al encadenamiento simple (las zonas se alargan por toda la calle). Como un mismo bache
grabado en varios recorridos cuenta varias veces, una zona con muchos baches pero pocos registros distintos suele
ser el mismo punto repetido. En la Fase 6 se podrá guardar el valor definitivo en los ajustes.

## Modo de conducción y alertas (Fase 5)

Si vienes de la Fase 4, descomprime encima, reinicia el backend y, en `frontend`, reinicia `npm run dev`. No hay
dependencias nuevas.

En **Conducción** pulsa **Iniciar con GPS**. La pantalla es mínima y legible de un vistazo: un panel de color arriba
(verde azulado = vía despejada, naranja/rojo/verde = bache de severidad media/alta/baja, violeta = zona crítica), la
distancia en grande, la velocidad y el botón **Detener**. El mapa pequeño de fondo se puede ocultar en **Alertas**.

**Cómo decide cuándo avisar** (el motor corre en el dispositivo, `src/conduccion/motor.js`):

- Solo avisa de lo que está **adelante** (a ±60° del sentido de marcha) y a menos de la distancia de aviso.
  Esa distancia es el valor que configuras (50 a 500 m, por defecto 150) o, si es mayor, lo que recorres en unos
  6 segundos: a más velocidad el aviso se adelanta solo.
- Cada bache o zona se avisa **una vez**. Se vuelve a armar al alejarse más del doble de la distancia o al pasarlo y
  dar la vuelta.
- Varios baches seguidos se avisan juntos («3 baches adelante…»).
- Al acercarte a una **zona crítica** se avisa la zona (a unos 2 × la distancia de aviso) y dentro de ella ya no se
  avisa bache por bache; el panel indica «En zona crítica».
- **Detenido** (menos de ~5 km/h) no avisa: evita repetir avisos en un semáforo.
- Se ignoran lecturas de GPS con precisión peor que 50 m.
- El GPS no distingue carriles, así que los avisos son por **zona de la vía**, no por carril.

**Ajustes** (sección **Alertas**; se guardan en el dispositivo): distancia de aviso, severidad mínima (todas, media y
alta, solo alta), zonas críticas sí/no, voz, tono y vibración. El tono es más agudo y repetido cuanto más severo.
La sección **Alertas** también muestra el **historial** de avisos (los últimos 200).

**Probar sin conducir.** En la parte de abajo de **Conducción** elige una zona, una velocidad y pulsa **Simular
recorrido**: el sistema recorre una recta que atraviesa la zona (500 m antes y 200 m después) y emite los avisos
reales, con voz, tono e historial (marcados como «simulado»).

**Límites que conviene conocer**
- El GPS del navegador solo funciona con **https o en `localhost`**. Abrir el sitio desde el celular por la IP de tu PC
  (`http://192.168…`) no da GPS; eso lo resuelve la app Android (Fase 7). Mientras tanto, prueba en la PC con el simulador.
- La voz usa la síntesis del navegador; si el sistema no tiene voz en español, usará la que haya. Los navegadores solo
  dejan sonar tras pulsar **Iniciar**.
- La pantalla se mantiene encendida si el navegador lo permite (Wake Lock). Con la pantalla apagada o la app en segundo
  plano, un navegador puede dejar de recibir GPS; la app Android (Fase 7) lo hará con un servicio en primer plano.
- Los baches se cargan al abrir la sección; para ver baches recién importados, vuelve a entrar en **Conducción**.
- Un mismo bache grabado en varios recorridos puede avisarse más de una vez si sus coordenadas difieren unos metros.

Pruebas del motor de alertas (sin navegador): en `frontend`, `npm test`.

## Planificador de rutas A → B (Fase 5B)

Para calcular rutas se usa **GraphHopper**, un motor de código abierto que corre en tu equipo con datos de
OpenStreetMap (sin Docker ni servicios de pago). Sigue **`graphhopper/README.md`**: instalar Java 17+, descargar el
`.jar` y el mapa de Ecuador a esa carpeta y ejecutar `iniciar_graphhopper.bat` (la primera vez tarda varios minutos).
En **Inicio**, el indicador «Motor de rutas» pasa a verde cuando está en marcha. Todo lo demás funciona sin él.

Si vienes de la Fase 5: descomprime encima, en `backend` ejecuta `pip install -r requirements.txt` y reinicia el
backend; en `frontend` reinicia `npm run dev`.

En **Conducción → Planificar ruta**:

1. Elige el **origen (A)** y el **destino (B)**: escribe una dirección y pulsa 🔍, usa 📍 para tu ubicación o pulsa
   en el mapa (primer toque = A, segundo = B). Los marcadores se pueden arrastrar.
2. Pulsa **Calcular ruta**. Se muestran hasta 3 rutas con tiempo, distancia, número de baches y de zonas críticas
   que cruzan. La ruta **recomendada** es la de menos riesgo (alta = 3, media = 2, baja = 1 por bache) entre las que
   no tardan más de 1,3 veces lo que la más rápida. Pulsa una ruta para verla con sus baches y zonas.
3. Pulsa **Iniciar conducción con esta ruta**, o **Probar esta ruta sin conducir** para simularla.

**Durante la conducción con ruta**
- Los avisos usan solo los baches y zonas **de tu ruta** (a menos de 30 m de su eje), no los de calles paralelas.
- El panel muestra lo próximo que hay («Próxima zona crítica en 1,2 km») y cuánto queda para llegar.
- Si te sales de la ruta (más de 60 m), el panel lo indica y vuelve a avisar de **todos** los baches cercanos, como
  en conducción libre; el botón **Recalcular ruta desde aquí** traza una ruta nueva hasta el mismo destino.
- Al llegar avisa y termina el seguimiento.

**Buscador de direcciones.** Usa Nominatim (OpenStreetMap): gratuito y sin clave, pero con uso moderado (solo busca al
pulsar 🔍, no autocompleta). Necesita internet. Para otro servidor, `VITE_GEOCODER_URL` en `frontend/.env`. Si falla,
puedes elegir los puntos pulsando en el mapa.

**Límites que conviene conocer**
- Las rutas son **en coche**, con calles y sentidos de OpenStreetMap; solo hay rutas dentro del mapa cargado
  (Ecuador). Si el motor solo encuentra una ruta razonable, no muestra alternativas.
- El riesgo es una suma de baches estimados, no una medición vial; un mismo bache grabado varias veces cuenta varias
  veces. Con GPS impreciso (la ubicación del bache es la de la cámara) un bache cercano puede quedar dentro o fuera
  del corredor de 30 m.
- Al recalcular se pide una sola ruta (la que el motor considera mejor), sin comparar riesgos.
- El GPS del navegador sigue requiriendo https o `localhost` (la app Android, Fase 7, lo resolverá).

## Estadísticas y ajustes (Fase 6)

Si vienes de la Fase 5B: descomprime encima y reinicia el backend (al arrancar crea solo la tabla nueva de ajustes; no
se pierde nada) y `npm run dev`. No hay dependencias nuevas.

**Estadísticas.** Totales, reparto por severidad y por origen (video o foto), confianza media, baches por mes
(apilados por severidad, en hora de Ecuador), calles o tramos con más baches, ciudades y zonas críticas principales.
Se pueden filtrar por fechas y ciudad. Cada fila tiene **Ver en el mapa**: abre el mapa ya filtrado por esa calle o
ciudad, o centrado en esa zona. Notas para leerlas bien:
- Los baches sin nombre de calle no aparecen en la tabla de calles (se indica cuántos son).
- Un mismo bache grabado en varios recorridos cuenta varias veces; la columna *Registros* de las zonas muestra en
  cuántas fotos o videos distintos se ven, y una zona con pocos registros suele ser un único punto repetido.
- La severidad es una estimación, no una medición vial.

**Ajustes** (menú «Ajustes»). Se guardan **en el servidor**, por lo que la web y Android usan los mismos valores:
- *Zonas críticas*: cercanía, densidad y tamaño mínimo. Muestra al instante cuántas zonas salen con esos valores.
  Son los valores con los que parten el mapa (sus controles siguen sirviendo para explorar sin guardar), las
  estadísticas, la conducción y el planificador de rutas.
- *Rutas*: ancho del corredor (a cuántos metros del eje de la ruta se cuenta un bache).
- Botones **Guardar**, **Descartar cambios** y **Valores de fábrica** (30 m, densidad 6, mínimo 8 baches, corredor 30 m).
- Además muestra el estado del sistema y enlaza a **Actualizar mapas de registros** y a los ajustes de alertas.

Los ajustes de **alertas** (distancia de aviso, severidad mínima, voz, tono, vibración, mapa en conducción) son propios de
cada dispositivo y siguen en la sección **Alertas**.

Cualquiera que llegue al servidor puede cambiar los ajustes compartidos: mientras el backend solo escuche en tu
equipo no hay problema; si lo expones en una red, activa la clave `API_TOKEN` (ver «App Android»).

## App Android (Fase 7)

La app es la misma interfaz web empaquetada con **Capacitor**, más plugins nativos: GPS en segundo plano (servicio en
primer plano con notificación), voz del teléfono, vibración y pantalla encendida. Los datos siguen en el servidor de tu
PC; la app guarda una copia local de baches, zonas y de la última ruta para poder avisarte sin conexión.

### Requisitos en la PC
- Node.js **22 o superior** (`node -v`; si tienes 20, instala la LTS nueva desde nodejs.org).
- **Android Studio** reciente (Otter 2025.2.1 o superior) con su SDK (se instala con el asistente).
- Teléfono Android 7.0 o superior con **Depuración USB** activada (Ajustes → Acerca del teléfono → toca 7 veces
  «Número de compilación»; luego Opciones de desarrollador → Depuración USB).

### 1. Preparar el proyecto Android
```powershell
cd frontend
npm install
npm run android:sync
npm run android:abrir
```
`android:sync` compila la web, la copia al proyecto Android y añade los permisos (ubicación, servicio en primer plano,
notificaciones, vibración, pantalla encendida y conexión http a tu red local). Se puede repetir cada vez que cambies el
frontend. `android:abrir` abre `frontend/android` en Android Studio (la primera vez descarga Gradle: tarda unos minutos).

### 2. Instalar en el teléfono
Conecta el teléfono por USB, acepta «Permitir depuración USB», elige tu teléfono en la barra superior de Android Studio
y pulsa **Run ▶**.

### 3. Que el teléfono llegue al backend
El teléfono y la PC deben estar en la **misma red Wi-Fi**. Arranca el backend escuchando en toda la red:
```powershell
cd backend
.\.venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8001
```
Permite el puerto en el Firewall de Windows (PowerShell **como administrador**):
```powershell
netsh advfirewall firewall add rule name="Vialidad Mapa 8001" dir=in action=allow protocol=TCP localport=8001
```
Averigua la IP de tu PC con `ipconfig` (línea «Dirección IPv4», por ejemplo `192.168.1.20`). En la app, la primera vez
se abre **Ajustes → Conexión con el servidor**: escribe `http://192.168.1.20:8001`, pulsa **Probar conexión** y luego
**Guardar conexión**.

### Clave de acceso (opcional, recomendada si compartes la red)
En `backend/.env` pon `API_TOKEN=una-clave-larga` y reinicia el backend. Desde entonces, importar datos y cambiar los
ajustes compartidos exige esa clave (la lectura del mapa sigue abierta). Escríbela en Ajustes → Conexión de la app.

### Primer uso en el teléfono
1. Acepta el permiso de **ubicación** (elige «Mientras se usa la app» o «Permitir siempre») y el de **notificaciones**.
2. En Android: Ajustes → Apps → Vialidad Mapa → Batería → **Sin restricciones**, para que el sistema no detenga el GPS
   con la pantalla apagada.
3. Abre **Conducción**; se guardan datos en el teléfono. Sin Wi-Fi sigue avisando con la última copia.

### Qué conviene verificar en tu teléfono (no puedo probarlo desde aquí)
- GPS con la app en primer plano y con la **pantalla apagada o en otra app**: el servicio nativo mantiene la app viva,
  pero cada fabricante gestiona la batería distinto (Xiaomi, Huawei y Samsung son los más estrictos).
- Voz en español (depende de las voces instaladas en el teléfono), vibración y que la pantalla no se apague.
- Modo avión o sin Wi-Fi: Conducción debe mostrar «datos guardados en el teléfono».

### Limitaciones
- Fuera de tu Wi-Fi el teléfono no alcanza el servidor de tu PC (para eso haría falta una VPN o un túnel, p. ej.
  Tailscale); con la copia local puedes conducir igualmente, pero sin actualizar datos.
- La conexión es http dentro de tu red local, no cifrada: no la uses en redes públicas.
- Planificar rutas A → B necesita GraphHopper corriendo en la PC y conexión con el servidor.
- El ícono es el de Capacitor por defecto; se cambia en Fase 8 si lo deseas.

## Pruebas

Usan una base **aparte**, que se crea sola (su nombre debe terminar en `_test`):

```powershell
cd backend
$env:TEST_DATABASE_URL="postgresql+psycopg://postgres:TU_PASSWORD@localhost:5432/baches_mapa_test"
pytest -q
```

## Plan de fases

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Análisis y planificación | Hecha |
| 2 | Estructura, backend, frontend y BD propia | Hecha |
| 3 | Importación y botón «Actualizar mapas de registros» | Hecha |
| 4 | Mapa interactivo | Hecha |
| 5 | Modo de conducción y alertas por zona | Hecha |
| 5B | Planificador de rutas A → B (motor de rutas) | Hecha |
| 6 | Estadísticas y configuración | Hecha |
| 7 | Adaptación Android (Capacitor) | **Esta entrega** |
| 8 | Pruebas y documentación | Pendiente |
