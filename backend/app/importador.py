"""Importación de baches desde el proyecto original (SOLO LECTURA sobre el origen).

Qué se importa: únicamente la clase `pothole`, de dos lugares del original:
  - fotos:  `detecciones` (clase pothole) unida a `capturas`  -> una fila por bache detectado en la foto;
  - videos: `video_hallazgos` (clase pothole) unida a `videos` -> una fila por bache distinto estimado.

Reglas:
  - Identidad = (fuente, tipo de origen, id de origen): reimportar nunca duplica.
  - Cada registro del origen cae en EXACTAMENTE una categoría: nuevo, actualizado, sin cambios, descartado
    en el origen, omitido (sin GPS válido) o error.
  - Lo importado antes que ya no existe en el origen se marca `retirado_origen` (no se borra: hay trazabilidad).
  - La imagen de evidencia se COPIA a un almacenamiento propio (recorte alrededor del bache en las fotos), de modo
    que el mapa no dependa de que el origen conserve sus archivos.
  - Nada de esto escribe en el origen: las consultas son SELECT y la conexión se abre en modo solo lectura.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from geoalchemy2.elements import WKTElement
from PIL import Image, ImageDraw
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Bache, Fuente, Importacion, ImportacionError
from .severidad import calcular

LOTE = 100                       # cada cuántos registros se confirma (y se actualiza el progreso)
MAX_COPIA_BYTES = 8 * 1024 * 1024
LADO_MAX_RECORTE = 640

# Estructura mínima que debe tener el origen (no se suponen nombres: se comprueba antes de leer).
REQUERIDAS: dict[str, set[str]] = {
    "tramos": {"id", "nombre", "ciudad"},
    "capturas": {"id", "tramo_id", "fecha_captura", "lat", "lon", "origen_gps", "ruta_imagen", "ancho", "alto",
                 "modelo_version", "perfil", "parametros"},
    "detecciones": {"id", "captura_id", "clase", "confianza", "x1", "y1", "x2", "y2", "area_frac"},
    "videos": {"id", "tramo_id", "fecha_inicio", "ruta_gps", "modelo_version", "perfil", "parametros"},
    "video_hallazgos": {"id", "video_id", "clase", "t_ini", "t_fin", "n_apariciones", "conf_max", "area_max",
                        "ruta_imagen", "lat", "lon", "descartado"},
}

SQL_FOTOS = """
SELECT d.id AS origen_id, d.captura_id AS padre_id, d.confianza, d.x1, d.y1, d.x2, d.y2, d.area_frac,
       c.fecha_captura, c.lat, c.lon, c.origen_gps, c.ruta_imagen, c.ancho, c.alto,
       c.modelo_version, c.perfil, c.parametros, t.nombre AS tramo_nombre, t.ciudad
FROM detecciones d
JOIN capturas c ON c.id = d.captura_id
JOIN tramos t ON t.id = c.tramo_id
WHERE d.clase = 'pothole'
ORDER BY d.id
"""

SQL_VIDEOS = """
SELECT h.id AS origen_id, h.video_id AS padre_id, h.t_ini, h.t_fin, h.n_apariciones, h.conf_max, h.area_max,
       h.ruta_imagen, h.lat, h.lon, h.descartado,
       v.fecha_inicio, v.modelo_version, v.perfil, v.parametros, t.nombre AS tramo_nombre, t.ciudad
FROM video_hallazgos h
JOIN videos v ON v.id = h.video_id
JOIN tramos t ON t.id = v.tramo_id
WHERE h.clase = 'pothole'
ORDER BY h.id
"""

# La ruta GPS de cada video se pide una sola vez por video (no repetida en cada hallazgo).
SQL_RUTAS = """
SELECT DISTINCT v.id, v.ruta_gps
FROM videos v JOIN video_hallazgos h ON h.video_id = v.id
WHERE h.clase = 'pothole' AND v.ruta_gps IS NOT NULL
"""


class OrigenIncompatible(RuntimeError):
    pass


@dataclass
class Candidato:
    """Un bache del origen, ya normalizado (venga de una foto o de un video)."""
    origen_tipo: str
    origen_id: int
    padre_id: int
    lat: float | None
    lon: float | None
    gps_origen: str | None
    detectado_en: datetime
    confianza: float
    area_frac: float | None
    n_apariciones: int | None
    modelo_version: str | None
    perfil: str | None
    parametros: dict | None
    tramo_nombre: str | None
    ciudad: str | None
    ruta_rel: str | None                      # imagen en el storage del origen
    bbox: tuple[float, float, float, float] | None = None   # solo fotos
    img_size: tuple[int, int] | None = None                 # solo fotos
    rumbo: float | None = None
    descartado: bool = False

    @property
    def clave(self) -> tuple[str, int]:
        return (self.origen_tipo, self.origen_id)


# ───────────────────────── utilidades puras (se prueban por separado) ─────────────────────────

def coordenadas_validas(lat: float | None, lon: float | None) -> str | None:
    """None si son válidas; si no, el motivo para informar al usuario."""
    if lat is None or lon is None:
        return "Sin coordenadas GPS"
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return "Coordenadas no numéricas"
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return f"Coordenadas fuera de rango ({lat}, {lon})"
    if lat == 0 and lon == 0:
        return "Coordenadas (0, 0): GPS sin fijar"
    return None


def _metros(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distancia aproximada (m) entre dos puntos (lat, lon); suficiente para distancias cortas."""
    k = 111_320.0
    dy = (a[0] - b[0]) * k
    dx = (a[1] - b[1]) * k * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dx, dy)


def _rumbo(a: tuple[float, float], b: tuple[float, float]) -> float:
    f1, f2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    y = math.sin(dl) * math.cos(f2)
    x = math.cos(f1) * math.sin(f2) - math.sin(f1) * math.cos(f2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def rumbo_desde_ruta(ruta: list | None, lat: float, lon: float, min_m: float = 3.0, max_dist_m: float = 60.0) -> float | None:
    """Sentido de marcha (grados, 0 = norte) del vehículo al pasar por (lat, lon), deducido de la ruta GPS del video.

    None si la ruta no sirve: pocos puntos, punto demasiado lejos del bache o vehículo detenido (el rumbo con
    movimientos de pocos metros es ruido de GPS)."""
    try:
        pts = [(float(p[0]), float(p[1])) for p in (ruta or [])]
    except (TypeError, ValueError, IndexError):
        return None
    if len(pts) < 2:
        return None
    ref = (lat, lon)
    i = min(range(len(pts)), key=lambda k: _metros(pts[k], ref))
    if _metros(pts[i], ref) > max_dist_m:
        return None
    a = i
    while a > 0 and _metros(pts[a], pts[i]) < min_m:
        a -= 1
    b = i
    while b < len(pts) - 1 and _metros(pts[b], pts[i]) < min_m:
        b += 1
    if a == b or _metros(pts[a], pts[b]) < min_m:
        return None
    return round(_rumbo(pts[a], pts[b]), 1)


def ruta_segura(base: Path | None, rel: str | None) -> Path | None:
    """Resuelve `rel` dentro de `base`. None si no hay base, o si `rel` intenta salirse de ella."""
    if base is None or not rel:
        return None
    try:
        raiz = base.resolve()
        p = (raiz / rel).resolve()
    except (OSError, ValueError):
        return None
    if raiz != p and raiz not in p.parents:
        return None
    return p


def _json(txt: str | dict | None) -> dict | None:
    if txt is None:
        return None
    if isinstance(txt, dict):
        return txt
    try:
        d = json.loads(txt)
        return d if isinstance(d, dict) else None
    except (TypeError, ValueError):
        return None


def hash_contenido(c: Candidato) -> str:
    """Huella de todo lo que importa de un registro: si cambia algo en el origen, cambia la huella."""
    datos = {
        "lat": c.lat, "lon": c.lon, "gps": c.gps_origen, "fecha": c.detectado_en.isoformat(),
        "conf": c.confianza, "area": c.area_frac, "apar": c.n_apariciones, "modelo": c.modelo_version,
        "perfil": c.perfil, "param": c.parametros, "tramo": c.tramo_nombre, "ciudad": c.ciudad,
        "ruta": c.ruta_rel, "bbox": c.bbox, "rumbo": c.rumbo,
    }
    return hashlib.sha256(json.dumps(datos, sort_keys=True, default=str).encode()).hexdigest()


# ───────────────────────── evidencia ─────────────────────────

def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _recorte_foto(origen: Path, c: Candidato, destino: Path) -> None:
    """Recorte alrededor del bache, con su caja dibujada, a partir de la foto completa."""
    with Image.open(origen) as im:
        im = im.convert("RGB")
        w, h = im.size
        x1, y1, x2, y2 = c.bbox
        if c.img_size and c.img_size != (w, h) and c.img_size[0] and c.img_size[1]:
            sx, sy = w / c.img_size[0], h / c.img_size[1]       # si la foto se guardó con otro tamaño
            x1, x2, y1, y2 = x1 * sx, x2 * sx, y1 * sy, y2 * sy
        bw, bh = x2 - x1, y2 - y1
        mx, my = max(bw * 1.0, 60), max(bh * 1.0, 60)
        a, b = max(0, int(x1 - mx)), max(0, int(y1 - my))
        z, d = min(w, int(x2 + mx)), min(h, int(y2 + my))
        if z <= a or d <= b:
            raise ValueError("la caja del bache queda fuera de la imagen")
        rec = im.crop((a, b, z, d))
        ImageDraw.Draw(rec).rectangle([x1 - a, y1 - b, x2 - a, y2 - b], outline=(220, 38, 38),
                                      width=max(2, rec.width // 100))
        k = LADO_MAX_RECORTE / max(rec.size)
        if k < 1:
            rec = rec.resize((max(1, int(rec.width * k)), max(1, int(rec.height * k))), Image.LANCZOS)
        destino.parent.mkdir(parents=True, exist_ok=True)
        rec.save(destino, "JPEG", quality=86)


def copiar_evidencia(c: Candidato, base_origen: Path | None, base_destino: Path) -> tuple[str | None, str | None, str | None]:
    """Copia la evidencia al almacenamiento propio. Devuelve (ruta relativa, sha256, motivo_si_falla)."""
    if base_origen is None:
        return None, None, "ORIGEN_STORAGE_DIR no configurado"
    src = ruta_segura(base_origen, c.ruta_rel)
    if src is None:
        return None, None, "ruta de imagen no válida"
    if not src.is_file():
        return None, None, "imagen no encontrada en el origen"
    rel = f"evidencias/{c.origen_tipo}/{c.origen_id}.jpg"
    dst = base_destino / rel
    try:
        if c.origen_tipo == "foto":
            if c.bbox is None:
                return None, None, "foto sin caja del bache"
            _recorte_foto(src, c, dst)
        else:
            if src.stat().st_size > MAX_COPIA_BYTES:
                return None, None, "imagen demasiado grande"
            with Image.open(src) as im:
                im.verify()                      # comprueba que es una imagen válida antes de copiarla
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
        return rel, _sha256(dst), None
    except Exception as e:  # noqa: BLE001 — una imagen mala no debe detener la importación
        return None, None, f"no se pudo procesar la imagen ({type(e).__name__})"


# ───────────────────────── lectura del origen ─────────────────────────

def verificar_estructura(eng: Engine) -> None:
    with eng.connect() as con:
        filas = con.execute(
            text("SELECT table_name, column_name FROM information_schema.columns "
                 "WHERE table_schema = 'public' AND table_name = ANY(:t)"),
            {"t": list(REQUERIDAS)},
        ).all()
    hay: dict[str, set[str]] = {}
    for t, col in filas:
        hay.setdefault(t, set()).add(col)
    faltan = []
    for tabla, cols in REQUERIDAS.items():
        if tabla not in hay:
            faltan.append(f"tabla {tabla}")
        else:
            faltan += [f"{tabla}.{c}" for c in sorted(cols - hay[tabla])]
    if faltan:
        raise OrigenIncompatible(
            "La base del proyecto original no tiene la estructura esperada. Faltan: " + ", ".join(faltan[:12])
            + (" …" if len(faltan) > 12 else "")
            + ". Abre una vez el proyecto original con su versión actual (migra sus tablas) y reintenta. "
              "Si el usuario de lectura se creó antes, revisa que tenga SELECT sobre esas tablas."
        )


def extraer(eng: Engine) -> list[Candidato]:
    """Lee del origen todos los baches (con SELECT, en una transacción de solo lectura)."""
    out: list[Candidato] = []
    with eng.connect() as con:
        con.execute(text("SET TRANSACTION READ ONLY"))
        rutas: dict[int, list | None] = {}
        for vid, txt in con.execute(text(SQL_RUTAS)).all():
            try:
                rutas[vid] = json.loads(txt) if txt else None
            except (TypeError, ValueError):
                rutas[vid] = None

        for r in con.execute(text(SQL_FOTOS)).mappings():
            gps = r["origen_gps"] if r["lat"] is not None and r["origen_gps"] else ("manual" if r["lat"] is not None else None)
            out.append(Candidato(
                origen_tipo="foto", origen_id=r["origen_id"], padre_id=r["padre_id"], lat=r["lat"], lon=r["lon"],
                gps_origen=gps, detectado_en=r["fecha_captura"], confianza=float(r["confianza"]),
                area_frac=r["area_frac"], n_apariciones=None, modelo_version=r["modelo_version"], perfil=r["perfil"],
                parametros=_json(r["parametros"]), tramo_nombre=r["tramo_nombre"], ciudad=r["ciudad"],
                ruta_rel=r["ruta_imagen"], bbox=(r["x1"], r["y1"], r["x2"], r["y2"]), img_size=(r["ancho"], r["alto"]),
            ))

        for r in con.execute(text(SQL_VIDEOS)).mappings():
            medio = (float(r["t_ini"]) + float(r["t_fin"])) / 2.0
            fecha = r["fecha_inicio"] + timedelta(seconds=medio)
            c = Candidato(
                origen_tipo="video", origen_id=r["origen_id"], padre_id=r["padre_id"], lat=r["lat"], lon=r["lon"],
                gps_origen="gpx" if r["lat"] is not None else None, detectado_en=fecha, confianza=float(r["conf_max"]),
                area_frac=r["area_max"], n_apariciones=r["n_apariciones"], modelo_version=r["modelo_version"],
                perfil=r["perfil"], parametros=_json(r["parametros"]), tramo_nombre=r["tramo_nombre"],
                ciudad=r["ciudad"], ruta_rel=r["ruta_imagen"], descartado=bool(r["descartado"]),
            )
            if c.lat is not None and c.lon is not None and coordenadas_validas(c.lat, c.lon) is None:
                c.rumbo = rumbo_desde_ruta(rutas.get(r["padre_id"]), c.lat, c.lon)
            out.append(c)
    return out


# ───────────────────────── proceso de importación ─────────────────────────

class ImportacionEnCurso(RuntimeError):
    pass


def obtener_o_crear_fuente(db: Session, nombre: str, huella: str, storage: str) -> Fuente:
    f = db.scalar(select(Fuente).where(Fuente.nombre == nombre))
    if f is None:
        f = Fuente(nombre=nombre)
        db.add(f)
    f.huella, f.storage_dir = huella[:80], storage or None
    db.flush()
    return f


def crear_importacion(SessionFactory: sessionmaker, nombre: str, huella: str, storage: str) -> int:
    """Registra el inicio de una importación. Lanza ImportacionEnCurso si ya hay una activa."""
    with SessionFactory() as db:
        activa = db.scalar(select(Importacion.id).where(Importacion.estado == "en_curso"))
        if activa:
            raise ImportacionEnCurso(f"Ya hay una actualización en curso (n.º {activa}).")
        fuente = obtener_o_crear_fuente(db, nombre, huella, storage)
        imp = Importacion(fuente_id=fuente.id)
        db.add(imp)
        db.commit()
        return imp.id


def marcar_interrumpidas(SessionFactory: sessionmaker) -> int:
    """Al arrancar el servidor, una importación «en curso» quedó huérfana (se reinició): se marca como fallida."""
    with SessionFactory() as db:
        n = 0
        for imp in db.scalars(select(Importacion).where(Importacion.estado == "en_curso")):
            imp.estado, imp.terminada_en = "fallida", datetime.now(timezone.utc)
            imp.mensaje = "Interrumpida: el servidor se reinició mientras importaba. Vuelve a pulsar «Actualizar»."
            n += 1
        db.commit()
        return n


def _aplicar(b: Bache, c: Candidato, h: str, imp_id: int) -> None:
    puntaje, nivel_ = calcular(c.confianza, c.area_frac, c.n_apariciones)
    b.origen_padre_id = c.padre_id
    b.hash_contenido = h
    b.importacion_id = imp_id
    b.geom = WKTElement(f"POINT({c.lon} {c.lat})", srid=4326)
    b.gps_origen = c.gps_origen
    b.rumbo_grados = c.rumbo
    b.detectado_en = c.detectado_en
    b.confianza = min(max(c.confianza, 0.0), 1.0)
    b.area_frac = c.area_frac
    b.n_apariciones = c.n_apariciones
    b.modelo_version = c.modelo_version
    b.perfil = c.perfil
    b.parametros = c.parametros
    b.severidad_puntaje, b.severidad_nivel = puntaje, nivel_
    b.tramo_nombre = c.tramo_nombre
    b.ciudad = c.ciudad
    b.estado = "activo"


def ejecutar_importacion(
    SessionFactory: sessionmaker,
    eng_origen: Engine,
    importacion_id: int,
    base_origen: Path | None,
    base_destino: Path,
    cancelado: Callable[[], bool] | None = None,
) -> None:
    """Corre la importación completa. Nunca lanza: si algo falla, deja la importación como «fallida» con el motivo."""
    with SessionFactory() as db:
        imp = db.get(Importacion, importacion_id)
        try:
            verificar_estructura(eng_origen)
            candidatos = extraer(eng_origen)
            imp.encontrados = len(candidatos)
            db.commit()

            existentes = {(b.origen_tipo, b.origen_id): b
                          for b in db.scalars(select(Bache).where(Bache.fuente_id == imp.fuente_id))}
            vistos: set[tuple[str, int]] = set()

            for n, c in enumerate(candidatos, 1):
                vistos.add(c.clave)
                try:
                    with db.begin_nested():
                        _procesar(db, imp, c, existentes.get(c.clave), existentes, base_origen, base_destino)
                except Exception as e:  # noqa: BLE001 — un registro malo no detiene a los demás
                    imp.errores += 1
                    db.add(ImportacionError(importacion_id=imp.id, origen_tipo=c.origen_tipo, origen_id=c.origen_id,
                                            motivo=f"Error inesperado: {type(e).__name__}: {e}"[:200]))
                if n % LOTE == 0:
                    db.commit()

            # Lo que se importó antes y ya no existe en el origen (borrado allí): se conserva, marcado.
            for clave, b in existentes.items():
                if clave not in vistos and b.estado != "retirado_origen":
                    b.estado = "retirado_origen"
                    imp.retirados += 1

            imp.estado, imp.terminada_en = "completada", datetime.now(timezone.utc)
            db.commit()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            imp = db.get(Importacion, importacion_id)
            imp.estado, imp.terminada_en = "fallida", datetime.now(timezone.utc)
            imp.mensaje = (str(e) if isinstance(e, OrigenIncompatible) else f"{type(e).__name__}: {getattr(e, 'orig', e)}")[:1000]
            db.commit()


def _procesar(db: Session, imp: Importacion, c: Candidato, b: Bache | None, existentes: dict,
              base_origen: Path | None, base_destino: Path) -> None:
    # 1) Descartado a mano en el origen (solo videos): no se importa; si ya estaba, se marca.
    if c.descartado:
        imp.descartados += 1
        if b is not None and b.estado != "descartado_origen":
            b.estado = "descartado_origen"
        return

    # 2) Sin coordenadas utilizables: no se puede poner en el mapa.
    motivo = coordenadas_validas(c.lat, c.lon)
    if motivo:
        imp.omitidos += 1
        db.add(ImportacionError(importacion_id=imp.id, origen_tipo=c.origen_tipo, origen_id=c.origen_id, motivo=motivo))
        return

    h = hash_contenido(c)

    # 3) Ya importado y sin cambios.
    if b is not None and b.hash_contenido == h and b.estado == "activo":
        if b.ruta_evidencia is None:        # quizá antes no se pudo copiar la imagen: se reintenta
            rel, sha, why = copiar_evidencia(c, base_origen, base_destino)
            if rel:
                b.ruta_evidencia, b.evidencia_sha256 = rel, sha
                imp.actualizados += 1
                return
            imp.sin_evidencia += 1
        imp.sin_cambios += 1
        return

    # 4) Nuevo, o cambió algo en el origen, o se reactivó.
    nuevo = b is None
    if nuevo:
        b = Bache(fuente_id=imp.fuente_id, origen_tipo=c.origen_tipo, origen_id=c.origen_id)
        db.add(b)
    _aplicar(b, c, h, imp.id)
    rel, sha, why = copiar_evidencia(c, base_origen, base_destino)
    if rel:
        b.ruta_evidencia, b.evidencia_sha256 = rel, sha
    else:
        imp.sin_evidencia += 1
    db.flush()
    if nuevo:
        imp.nuevos += 1
    else:
        imp.actualizados += 1
