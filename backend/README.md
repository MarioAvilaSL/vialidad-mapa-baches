# Vialidad Mapa · Baches

Plataforma web y Android para consultar en un mapa los baches detectados por el proyecto
**Vialidad · YOLO26** y recibir avisos de zonas con baches mientras se conduce.

> **Estado: Fase 3 de 8 (importación y sincronización).** Funciona el botón «Actualizar mapas de registros», que
> importa los baches del proyecto original. El mapa (Fase 4) y el resto se construyen en las fases siguientes.

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
  sql/          origen_usuario_lectura.sql: usuario de solo lectura para el proyecto original
```

## Requisitos (Windows)

- Python 3.11 a 3.13
- Node.js 20 o superior (versión LTS, desde nodejs.org)
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
| 3 | Importación y botón «Actualizar mapas de registros» | **Esta entrega** |
| 4 | Mapa interactivo | Pendiente |
| 5 | Modo de conducción y alertas por zona | Pendiente |
| 5B | Planificador de rutas A → B (motor de rutas) | Pendiente |
| 6 | Estadísticas y configuración | Pendiente |
| 7 | Adaptación Android (Capacitor) | Pendiente |
| 8 | Pruebas y documentación | Pendiente |
