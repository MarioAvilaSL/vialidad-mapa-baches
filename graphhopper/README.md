# Motor de rutas (GraphHopper) · Fase 5B

El planificador de rutas A → B usa **GraphHopper**, un motor de rutas de código abierto que corre en tu propio
equipo con datos de OpenStreetMap. No usa servicios de pago ni envía tus rutas a terceros. No necesita Docker.

El resto de la aplicación funciona igual sin él: solo el planificador de rutas lo necesita.

## Instalación (una sola vez)

**1. Java 17 o superior.** Descarga e instala *Temurin* (JDK o JRE) desde <https://adoptium.net>.
Instala la versión de **64 bits** (en Windows: *Windows x64*). Comprueba en PowerShell: `java -version`; debe decir
17 o más y contener `64-Bit Server VM`. Un Java de 32 bits da el error «Invalid maximum heap size» y no sirve.

**2. El programa.** Descarga `graphhopper-web-11.1.jar` desde
<https://github.com/graphhopper/graphhopper/releases/tag/11.1> (sección *Assets*) y guárdalo **en esta carpeta**
(`graphhopper`).

**3. El mapa de Ecuador.** Descarga `ecuador-latest.osm.pbf` desde
<https://download.geofabrik.de/south-america/ecuador.html> (enlace «ecuador-latest.osm.pbf») y guárdalo
**en esta carpeta**. Es de OpenStreetMap y se actualiza a diario; puedes volver a descargarlo cuando quieras
mejorar el mapa (ver «Actualizar el mapa»).

Al terminar, esta carpeta debe contener: `config.yml`, `iniciar_graphhopper.bat`, `graphhopper-web-11.1.jar` y
`ecuador-latest.osm.pbf`.

## Uso

Doble clic en `iniciar_graphhopper.bat` (o `.\iniciar_graphhopper.bat` en PowerShell).

- La **primera vez** procesa el mapa de Ecuador: tarda varios minutos y usa bastante memoria. No cierres la ventana.
  Se crea la carpeta `graph-cache` con el resultado.
- Las **siguientes veces** arranca en segundos.
- Está listo cuando la ventana muestra `Started Server`. Déjala abierta mientras uses el planificador.
- Para comprobarlo, abre <http://localhost:8989/health>: debe decir `OK`. En **Inicio** de la aplicación, el indicador
  «Motor de rutas» pasa a verde.

Si aparece `OutOfMemoryError`, edita `iniciar_graphhopper.bat` y cambia `-Xmx2g` por `-Xmx3g` o `-Xmx4g`.

## Actualizar el mapa

Cierra GraphHopper, descarga de nuevo `ecuador-latest.osm.pbf` (reemplaza el archivo), **borra la carpeta
`graph-cache`** y arranca otra vez.

## Si cambias el puerto o lo pones en otro equipo

En `backend\.env` define `ROUTING_URL=http://direccion:puerto` y reinicia el backend.

## Notas

- Calcula rutas **en coche** y ofrece hasta 3 alternativas. Los datos de calles y sentidos son los de OpenStreetMap:
  si una calle está mal en OpenStreetMap, la ruta también lo estará.
- Los archivos `.jar`, `.pbf` y `graph-cache` no forman parte del proyecto (son grandes y se descargan aparte).
