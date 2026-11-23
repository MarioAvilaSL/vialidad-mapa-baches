"""Planificador de rutas A → B: pide las rutas al motor (GraphHopper) y calcula, con PostGIS, qué baches y zonas
críticas hay a lo largo de cada una."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import ajustes, routing
from ..db import get_db
from ..models import Bache
from ..zonas import calcular_zonas

router = APIRouter(prefix="/api/rutas", tags=["rutas"])

PESO = {"alta": 3, "media": 2, "baja": 1}
MAX_BACHES_POR_RUTA = 5000
TOLERANCIA_TIEMPO = 1.3       # la ruta recomendada no puede tardar más de 1,3 veces la más rápida


class Punto(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class PlanificarIn(BaseModel):
    origen: Punto
    destino: Punto
    alternativas: int = Field(3, ge=1, le=3, description="Cuántas rutas pedir (1 a 3)")
    # Si no se indican, se usan los ajustes guardados (sección Ajustes)
    ancho_m: float | None = Field(None, ge=5, le=100, description="Distancia máxima de un bache al eje de la ruta para contarlo")
    eps_m: float | None = Field(None, ge=5, le=1000)
    min_vecinos: int | None = Field(None, ge=2, le=50)
    min_baches: int | None = Field(None, ge=2, le=500)

    @model_validator(mode="after")
    def _distintos(self):
        if abs(self.origen.lat - self.destino.lat) < 1e-5 and abs(self.origen.lon - self.destino.lon) < 1e-5:
            raise ValueError("El origen y el destino son el mismo punto.")
        return self


@router.get("/estado")
def estado_motor():
    """Si el motor de rutas está en marcha."""
    return routing.estado()


_LINEA = "ST_SetSRID(ST_GeomFromGeoJSON(:linea), 4326)"

SQL_BACHES = text(f"""
WITH l AS (SELECT {_LINEA} AS g)
SELECT b.id, b.severidad_nivel AS sev, ST_Y(b.geom::geometry) AS lat, ST_X(b.geom::geometry) AS lon,
       ST_LineLocatePoint(l.g, b.geom::geometry) AS frac, ST_Distance(b.geom, l.g::geography) AS lateral_m
FROM baches b, l
WHERE b.estado = 'activo' AND ST_DWithin(b.geom, l.g::geography, :ancho)
ORDER BY frac
LIMIT :limite
""")

# Para cada zona: posición a lo largo de la ruta donde se entra (o del punto más cercano si solo la roza)
SQL_ZONAS = text(f"""
WITH l AS (SELECT {_LINEA} AS g),
z AS (SELECT gj, ord, ST_SetSRID(ST_GeomFromGeoJSON(gj), 4326) AS zg
      FROM unnest(CAST(:zonas AS text[])) WITH ORDINALITY AS t(gj, ord))
SELECT z.ord - 1 AS i, ST_Intersects(l.g, z.zg) AS cruza,
       COALESCE(
         (SELECT min(ST_LineLocatePoint(l.g, CASE WHEN GeometryType(d.geom) = 'POINT' THEN d.geom ELSE ST_StartPoint(d.geom) END))
            FROM ST_Dump(ST_Intersection(l.g, z.zg)) d),
         ST_LineLocatePoint(l.g, ST_ClosestPoint(l.g, z.zg))) AS frac,
       ST_Distance(z.zg::geography, l.g::geography) AS lateral_m
FROM z, l
WHERE ST_DWithin(z.zg::geography, l.g::geography, :ancho)
ORDER BY frac
""")


def _corredor(db: Session, coords: list, zonas: list[dict], ancho: float) -> dict:
    linea = json.dumps({"type": "LineString", "coordinates": coords})
    largo = db.scalar(text(f"SELECT ST_Length({_LINEA}::geography)"), {"linea": linea}) or 0.0
    baches = [
        {"id": r.id, "lat": r.lat, "lon": r.lon, "severidad": r.sev, "desde_m": round(r.frac * largo, 1),
         "lateral_m": round(r.lateral_m, 1)}
        for r in db.execute(SQL_BACHES, {"linea": linea, "ancho": ancho, "limite": MAX_BACHES_POR_RUTA})
    ]
    en_ruta = []
    if zonas:
        filas = db.execute(SQL_ZONAS, {"linea": linea, "ancho": ancho, "zonas": [json.dumps(z["geom"]) for z in zonas]})
        for r in filas:
            z = zonas[r.i]
            en_ruta.append({**{k: z[k] for k in ("n", "alta", "media", "baja", "registros", "tramo", "ciudad", "lat", "lon")},
                            "geometry": z["geom"], "cruza": r.cruza, "desde_m": round(r.frac * largo, 1),
                            "lateral_m": round(r.lateral_m, 1)})
    return {"baches": baches, "zonas": en_ruta, "largo_m": largo}


@router.post("/planificar")
def planificar(datos: PlanificarIn, db: Session = Depends(get_db)):
    """Rutas de A a B con los baches y zonas críticas de cada una.

    Para cada ruta: `baches` y `zonas` son los que están a menos de `ancho_m` de su eje, con `desde_m` (distancia
    recorrida desde el origen hasta ellos). `riesgo` suma 3, 2 o 1 por cada bache de severidad alta, media o baja.
    `recomendada` es la ruta con menos riesgo entre las que no tardan más de 1,3 veces la más rápida.
    """
    try:
        rutas = routing.calcular((datos.origen.lat, datos.origen.lon), (datos.destino.lat, datos.destino.lon), datos.alternativas)
    except routing.RutasError as e:
        raise HTTPException(e.status, e.mensaje) from e

    g = ajustes.leer(db)
    ancho = g["ancho_m"] if datos.ancho_m is None else datos.ancho_m
    eps_m = g["eps_m"] if datos.eps_m is None else datos.eps_m
    min_vecinos = g["min_vecinos"] if datos.min_vecinos is None else datos.min_vecinos
    min_baches = g["min_baches"] if datos.min_baches is None else datos.min_baches
    zonas = calcular_zonas(db, [Bache.estado == "activo"], eps_m, min_vecinos, min_baches)
    salida = []
    for i, r in enumerate(rutas):
        c = _corredor(db, r["coords"], zonas, ancho)
        n = {s: sum(1 for b in c["baches"] if b["severidad"] == s) for s in PESO}
        riesgo = sum(PESO[s] * k for s, k in n.items())
        km = max(r["distancia_m"] / 1000.0, 0.05)
        salida.append({
            "indice": i, "distancia_m": round(r["distancia_m"]), "tiempo_s": round(r["tiempo_s"]),
            "geometria": {"type": "LineString", "coordinates": r["coords"]},
            "baches": c["baches"], "zonas": c["zonas"],
            "resumen": {
                "baches": len(c["baches"]), "alta": n["alta"], "media": n["media"], "baja": n["baja"],
                "zonas": len(c["zonas"]), "riesgo": riesgo, "riesgo_por_km": round(riesgo / km, 2),
                "truncado": len(c["baches"]) >= MAX_BACHES_POR_RUTA,
            },
        })
    mas_rapida = min(range(len(salida)), key=lambda k: salida[k]["tiempo_s"])
    limite = salida[mas_rapida]["tiempo_s"] * TOLERANCIA_TIEMPO
    candidatas = [k for k, s in enumerate(salida) if s["tiempo_s"] <= limite]
    recomendada = min(candidatas, key=lambda k: (salida[k]["resumen"]["riesgo"], salida[k]["tiempo_s"]))
    return {
        "origen": datos.origen.model_dump(), "destino": datos.destino.model_dump(), "ancho_m": ancho,
        "mas_rapida": mas_rapida, "recomendada": recomendada,
        "parametros_zonas": {"eps_m": eps_m, "min_vecinos": min_vecinos, "min_baches": min_baches},
        "rutas": salida,
    }
