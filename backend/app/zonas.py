"""Zonas críticas: concentraciones de baches calculadas con PostGIS (DBSCAN por densidad).

Se usan tanto en el mapa (/api/zonas) como en el planificador de rutas (qué zonas cruza cada ruta).
"""
import json
import math

from sqlalchemy import case, func, literal_column, select
from sqlalchemy.orm import Session

from .models import Bache

# La columna `geom` es geography; para extraer coordenadas y agrupar se usa su versión geometry.
GEOM = literal_column("baches.geom::geometry")


def calcular_zonas(db: Session, conds: list, eps_m: float, min_vecinos: int, min_baches: int) -> list[dict]:
    """Zonas con al menos `min_baches` baches, de mayor a menor. Cada una: n, alta, media, baja, registros, tramo,
    ciudad, lat, lon (centro) y geom (contorno GeoJSON)."""
    lat_media = db.scalar(select(func.avg(func.ST_Y(GEOM))).where(*conds))
    if lat_media is None:
        return []

    # Se agrupa en EPSG:3857 (metros). Esa proyección estira las distancias por 1/cos(lat): se compensa con la
    # latitud media de los datos, lo que es exacto a escala local (la de una ciudad).
    k = 1.0 / max(math.cos(math.radians(lat_media)), 0.05)
    g = func.ST_Transform(GEOM, 3857)
    f = select(
        Bache.severidad_nivel.label("sev"), Bache.tramo_nombre.label("tramo"), Bache.ciudad.label("ciudad"),
        func.concat(Bache.origen_tipo, ":", Bache.origen_padre_id).label("registro"), g.label("g"),
    ).where(*conds).subquery()
    c = select(
        f.c.sev, f.c.tramo, f.c.ciudad, f.c.registro, f.c.g,
        func.ST_ClusterDBSCAN(f.c.g, eps_m * k, min_vecinos).over().label("cid"),
    ).subquery()
    # Círculo de 0,6·eps alrededor de cada bache: los círculos de baches vecinos (a menos de eps) se solapan,
    # y su unión es el contorno de la zona.
    contorno = func.ST_Transform(func.ST_Union(func.ST_Buffer(c.c.g, 0.6 * eps_m * k)), 4326)
    centro = func.ST_Transform(func.ST_Centroid(func.ST_Collect(c.c.g)), 4326)
    filas = db.execute(
        select(
            c.c.cid, func.count().label("n"),
            func.count(case((c.c.sev == "alta", 1))).label("alta"),
            func.count(case((c.c.sev == "media", 1))).label("media"),
            func.count(case((c.c.sev == "baja", 1))).label("baja"),
            func.count(func.distinct(c.c.registro)).label("registros"),
            func.mode().within_group(c.c.tramo).label("tramo"),
            func.mode().within_group(c.c.ciudad).label("ciudad"),
            func.ST_AsGeoJSON(contorno, 6).label("geom"),
            func.ST_Y(centro).label("lat"), func.ST_X(centro).label("lon"),
        ).where(c.c.cid.is_not(None)).group_by(c.c.cid).having(func.count() >= min_baches).order_by(func.count().desc())
    ).all()
    return [
        {"n": r.n, "alta": r.alta, "media": r.media, "baja": r.baja, "registros": r.registros, "tramo": r.tramo,
         "ciudad": r.ciudad, "lat": r.lat, "lon": r.lon, "geom": json.loads(r.geom)}
        for r in filas
    ]
