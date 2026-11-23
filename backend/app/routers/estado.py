from pathlib import Path

from fastapi import APIRouter, Depends, Header
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import routing
from ..config import settings
from ..db import engine_origen, get_db
from ..models import Bache
from ..seguridad import clave_valida, requiere_clave

router = APIRouter(prefix="/api", tags=["estado"])


def _estado_origen() -> dict:
    """Comprueba (solo lectura) si se puede llegar a la BD del proyecto original."""
    eng = engine_origen()
    storage = bool(settings.origen_storage_dir) and Path(settings.origen_storage_dir).is_dir()
    if eng is None:
        return {"configurado": False, "alcanzable": False, "storage": storage,
                "detalle": "ORIGEN_DATABASE_URL no está configurada."}
    try:
        with eng.connect() as con:
            con.execute(text("SELECT 1"))
        return {"configurado": True, "alcanzable": True, "storage": storage, "detalle": None}
    except Exception as e:  # noqa: BLE001  (se informa al usuario, no se propaga)
        return {"configurado": True, "alcanzable": False, "storage": storage,
                "detalle": str(getattr(e, "orig", e)).strip()[:200]}
    finally:
        eng.dispose()


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Estado de los componentes: API, base de datos propia, PostGIS y conexión de solo lectura al original."""
    try:
        postgis = db.scalar(text("SELECT postgis_version()"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db.rollback()
        postgis, db_ok = None, False
    return {"api": True, "db": db_ok, "postgis": postgis, "origen": _estado_origen(), "rutas": routing.estado()}


@router.get("/acceso")
def acceso(x_clave: str | None = Header(None, alias="X-Clave")):
    """¿Pide el servidor clave para modificar datos y la que se envía es correcta? (la usa la pantalla de conexión de la app)"""
    return {"requiere_clave": requiere_clave(), "clave_valida": clave_valida(x_clave)}


@router.get("/config")
def config():
    """Valores no sensibles que necesita la interfaz."""
    return {"timezone": settings.timezone, "version": "0.1.0"}


@router.get("/resumen")
def resumen(db: Session = Depends(get_db)):
    """Conteos básicos para el panel de inicio (se ampliará en las fases siguientes)."""
    total = db.scalar(select(func.count()).select_from(Bache)) or 0
    activos = db.scalar(select(func.count()).select_from(Bache).where(Bache.estado == "activo")) or 0
    ultima = db.scalar(select(func.max(Bache.importado_en)))
    act = Bache.estado == "activo"
    por_sev = dict(db.execute(select(Bache.severidad_nivel, func.count()).where(act).group_by(Bache.severidad_nivel)).all())
    por_origen = dict(db.execute(select(Bache.origen_tipo, func.count()).where(act).group_by(Bache.origen_tipo)).all())
    con_evidencia = db.scalar(select(func.count()).select_from(Bache).where(act, Bache.ruta_evidencia.is_not(None))) or 0
    return {
        "baches_total": total, "baches_activos": activos, "ultima_importacion": ultima,
        "por_severidad": {k: por_sev.get(k, 0) for k in ("alta", "media", "baja")},
        "por_origen": {k: por_origen.get(k, 0) for k in ("foto", "video")},
        "con_evidencia": con_evidencia,
    }
