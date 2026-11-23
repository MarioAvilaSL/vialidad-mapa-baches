"""API del mapa: baches en GeoJSON, filtros, detalle de cada bache y zonas críticas.

Solo se muestran baches con estado «activo» (no los descartados ni los retirados en el original).
Todos los filtros se comparten entre la lista de baches y las zonas críticas, de modo que las zonas
siempre reflejan lo que el usuario está viendo.
"""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from .. import ajustes
from ..config import settings
from ..db import get_db
from ..models import Bache
from ..zonas import GEOM, calcular_zonas

router = APIRouter(prefix="/api", tags=["mapa"])

LIMITE_DEFECTO = 20000


def _fecha_local(col):
    """Fecha del bache en la zona horaria configurada (Ecuador), no en UTC."""
    return cast(func.timezone(settings.timezone, col), Date)


def filtros(
    desde: date | None = Query(None, description="Fecha local mínima (AAAA-MM-DD), inclusive"),
    hasta: date | None = Query(None, description="Fecha local máxima (AAAA-MM-DD), inclusive"),
    confianza_min: float = Query(0.0, ge=0.0, le=1.0),
    severidad: list[Literal["baja", "media", "alta"]] | None = Query(None),
    origen: list[Literal["foto", "video"]] | None = Query(None),
    ciudad: str | None = Query(None, max_length=80),
    tramo: str | None = Query(None, max_length=120),
) -> list:
    conds = [Bache.estado == "activo"]
    if desde:
        conds.append(_fecha_local(Bache.detectado_en) >= desde)
    if hasta:
        conds.append(_fecha_local(Bache.detectado_en) <= hasta)
    if confianza_min > 0:
        conds.append(Bache.confianza >= confianza_min)
    if severidad:
        conds.append(Bache.severidad_nivel.in_(severidad))
    if origen:
        conds.append(Bache.origen_tipo.in_(origen))
    if ciudad:
        conds.append(Bache.ciudad == ciudad)
    if tramo:
        conds.append(Bache.tramo_nombre == tramo)
    return conds


@router.get("/baches")
def listar_baches(
    conds: list = Depends(filtros),
    limit: int = Query(LIMITE_DEFECTO, ge=1, le=50000),
    db: Session = Depends(get_db),
):
    """Baches como GeoJSON (coordenadas [lon, lat]). Si hay más que `limit`, se devuelven los más severos."""
    total = db.scalar(select(func.count()).select_from(Bache).where(*conds)) or 0
    filas = db.execute(
        select(
            Bache.id, Bache.severidad_nivel, Bache.severidad_puntaje, Bache.confianza, Bache.detectado_en,
            Bache.origen_tipo, Bache.tramo_nombre, Bache.ciudad,
            func.ST_X(GEOM).label("lon"), func.ST_Y(GEOM).label("lat"),
        )
        .where(*conds)
        .order_by(Bache.severidad_puntaje.desc().nulls_last(), Bache.id)
        .limit(limit)
    ).all()
    return {
        "type": "FeatureCollection",
        "total": total,
        "truncado": total > len(filas),
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [f.lon, f.lat]},
                "properties": {
                    "id": f.id, "severidad": f.severidad_nivel, "puntaje": f.severidad_puntaje,
                    "confianza": f.confianza, "fecha": f.detectado_en, "origen": f.origen_tipo,
                    "tramo": f.tramo_nombre, "ciudad": f.ciudad,
                },
            }
            for f in filas
        ],
    }


@router.get("/baches/filtros")
def opciones_de_filtros(db: Session = Depends(get_db)):
    """Valores disponibles para poblar los filtros de la interfaz (solo de baches activos)."""
    act = Bache.estado == "activo"
    ciudades = db.execute(
        select(Bache.ciudad, func.count()).where(act, Bache.ciudad.is_not(None)).group_by(Bache.ciudad).order_by(Bache.ciudad)
    ).all()
    tramos = db.execute(
        select(Bache.tramo_nombre, Bache.ciudad, func.count()).where(act, Bache.tramo_nombre.is_not(None))
        .group_by(Bache.tramo_nombre, Bache.ciudad).order_by(Bache.tramo_nombre)
    ).all()
    f = _fecha_local(Bache.detectado_en)
    fmin, fmax = db.execute(select(func.min(f), func.max(f)).where(act)).one()
    return {
        "total": db.scalar(select(func.count()).select_from(Bache).where(act)) or 0,
        "ciudades": [{"nombre": c, "n": n} for c, n in ciudades],
        "tramos": [{"nombre": t, "ciudad": c, "n": n} for t, c, n in tramos],
        "fecha_min": fmin, "fecha_max": fmax,
    }


@router.get("/baches/{bache_id}")
def detalle_bache(bache_id: int, db: Session = Depends(get_db)):
    """Todos los datos de un bache, para el panel de detalle (incluye la imagen de evidencia)."""
    b = db.get(Bache, bache_id)
    if not b:
        raise HTTPException(404, "Bache no encontrado.")
    lon, lat = db.execute(select(func.ST_X(GEOM), func.ST_Y(GEOM)).where(Bache.id == bache_id)).one()
    return {
        "id": b.id, "estado": b.estado, "lat": lat, "lon": lon, "gps_origen": b.gps_origen,
        "rumbo_grados": b.rumbo_grados, "detectado_en": b.detectado_en, "confianza": b.confianza,
        "area_frac": b.area_frac, "n_apariciones": b.n_apariciones,
        "severidad": {"nivel": b.severidad_nivel, "puntaje": b.severidad_puntaje},
        "origen": {"tipo": b.origen_tipo, "id": b.origen_id}, "modelo_version": b.modelo_version, "perfil": b.perfil,
        "tramo": b.tramo_nombre, "ciudad": b.ciudad,
        "evidencia_url": f"/media/{b.ruta_evidencia}" if b.ruta_evidencia else None,
        "importado_en": b.importado_en, "actualizado_en": b.actualizado_en,
    }


@router.get("/zonas")
def zonas_criticas(
    conds: list = Depends(filtros),
    eps_m: float | None = Query(None, ge=5, le=1000, description="Radio de vecindad (m). Por defecto, el ajuste guardado"),
    min_vecinos: int | None = Query(None, ge=2, le=50, description="Baches (contándose a sí mismo) a menos de eps_m para que un punto sea «denso». Por defecto, el ajuste guardado"),
    min_baches: int | None = Query(None, ge=2, le=500, description="Mínimo de baches que debe tener una zona. Por defecto, el ajuste guardado"),
    db: Session = Depends(get_db),
):
    """Zonas con una concentración alta de baches (agrupación por densidad, DBSCAN, hecha en PostGIS).

    Un bache es «denso» si tiene al menos `min_vecinos` baches (contándose a sí mismo) a menos de `eps_m` metros.
    Las zonas son los conjuntos de baches densos conectados entre sí, más los baches que tocan a alguno de ellos.
    Solo se devuelven las zonas con al menos `min_baches` baches. Así una calle con baches aislados no es una
    zona, y una ciudad entera tampoco: hace falta una concentración real.

    Con `min_vecinos=2` se obtiene el encadenamiento simple (cada bache a menos de `eps_m` de otro), que en una
    ciudad con muchos recorridos tiende a unir calles enteras en una sola zona.

    El contorno es la unión de un círculo alrededor de cada bache, por lo que sigue la forma de la calle.
    Cada zona informa su mezcla de severidades, el tramo y la ciudad más frecuentes y en cuántos registros
    de origen distintos (fotos o videos) se ven sus baches: un mismo bache grabado en varios recorridos
    cuenta varias veces, y ese dato ayuda a distinguirlo de una calle realmente llena de baches.
    """
    guardado = ajustes.leer(db)
    eps_m = guardado["eps_m"] if eps_m is None else eps_m
    min_vecinos = guardado["min_vecinos"] if min_vecinos is None else min_vecinos
    min_baches = guardado["min_baches"] if min_baches is None else min_baches
    zonas = calcular_zonas(db, conds, eps_m, min_vecinos, min_baches)
    return {
        "type": "FeatureCollection",
        "parametros": {"eps_m": eps_m, "min_vecinos": min_vecinos, "min_baches": min_baches},
        "features": [
            {
                "type": "Feature", "geometry": z["geom"],
                "properties": {k: z[k] for k in ("n", "alta", "media", "baja", "registros", "tramo", "ciudad", "lat", "lon")},
            }
            for z in zonas
        ],
    }
