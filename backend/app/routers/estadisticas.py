"""Estadísticas de los baches importados. Aceptan los mismos filtros que el mapa."""
from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .. import ajustes as aj
from ..config import settings
from ..db import get_db
from ..models import Bache
from ..zonas import calcular_zonas
from .baches import _fecha_local, filtros

router = APIRouter(prefix="/api", tags=["estadisticas"])

TOP = 10


def _por_nivel():
    return (
        func.count().label("n"),
        func.count(case((Bache.severidad_nivel == "alta", 1))).label("alta"),
        func.count(case((Bache.severidad_nivel == "media", 1))).label("media"),
        func.count(case((Bache.severidad_nivel == "baja", 1))).label("baja"),
    )


@router.get("/estadisticas")
def estadisticas(conds: list = Depends(filtros), db: Session = Depends(get_db)):
    """Resumen estadístico de los baches activos que cumplen los filtros."""
    total = db.scalar(select(func.count()).select_from(Bache).where(*conds)) or 0
    por_sev = dict(db.execute(select(Bache.severidad_nivel, func.count()).where(*conds).group_by(Bache.severidad_nivel)).all())
    por_origen = dict(db.execute(select(Bache.origen_tipo, func.count()).where(*conds).group_by(Bache.origen_tipo)).all())
    conf = db.scalar(select(func.avg(Bache.confianza)).where(*conds))
    con_evidencia = db.scalar(select(func.count()).select_from(Bache).where(*conds, Bache.ruta_evidencia.is_not(None))) or 0
    fmin, fmax = db.execute(select(func.min(_fecha_local(Bache.detectado_en)), func.max(_fecha_local(Bache.detectado_en))).where(*conds)).one()

    mes = func.to_char(func.timezone(settings.timezone, Bache.detectado_en), "YYYY-MM")
    por_mes = [
        {"mes": r.mes, "n": r.n, "alta": r.alta, "media": r.media, "baja": r.baja}
        for r in db.execute(select(mes.label("mes"), *_por_nivel()).where(*conds, Bache.detectado_en.is_not(None))
                            .group_by(mes).order_by(mes)).all()
    ]
    por_ciudad = [
        {"nombre": r.ciudad, "n": r.n, "alta": r.alta, "media": r.media, "baja": r.baja}
        for r in db.execute(select(Bache.ciudad, *_por_nivel()).where(*conds, Bache.ciudad.is_not(None))
                            .group_by(Bache.ciudad).order_by(func.count().desc(), Bache.ciudad).limit(TOP)).all()
    ]
    por_tramo = [
        {"nombre": r.tramo_nombre, "ciudad": r.ciudad, "n": r.n, "alta": r.alta, "media": r.media, "baja": r.baja}
        for r in db.execute(select(Bache.tramo_nombre, Bache.ciudad, *_por_nivel()).where(*conds, Bache.tramo_nombre.is_not(None))
                            .group_by(Bache.tramo_nombre, Bache.ciudad)
                            .order_by(func.count().desc(), Bache.tramo_nombre).limit(TOP)).all()
    ]
    sin_calle = db.scalar(select(func.count()).select_from(Bache).where(*conds, Bache.tramo_nombre.is_(None))) or 0

    valores = aj.leer(db)
    zonas = calcular_zonas(db, conds, valores["eps_m"], valores["min_vecinos"], valores["min_baches"])
    return {
        "total": total,
        "por_severidad": {k: por_sev.get(k, 0) for k in ("alta", "media", "baja")},
        "por_origen": {k: por_origen.get(k, 0) for k in ("foto", "video")},
        "confianza_media": round(conf, 3) if conf is not None else None,
        "con_evidencia": con_evidencia, "sin_calle": sin_calle,
        "fecha_min": fmin, "fecha_max": fmax,
        "por_mes": por_mes, "por_ciudad": por_ciudad, "por_tramo": por_tramo,
        "zonas": {
            "total": len(zonas), "baches_en_zonas": sum(z["n"] for z in zonas), "parametros": valores,
            "principales": [
                {k: z[k] for k in ("n", "alta", "media", "baja", "registros", "tramo", "ciudad", "lat", "lon")}
                for z in zonas[:TOP]
            ],
        },
    }
