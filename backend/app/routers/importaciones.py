import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal, engine_origen, get_db
from ..importador import ImportacionEnCurso, crear_importacion, ejecutar_importacion
from ..models import Importacion, ImportacionError
from ..seguridad import exigir_clave

router = APIRouter(prefix="/api/importaciones", tags=["importaciones"])

_arranque = threading.Lock()   # evita que dos clics simultáneos lancen dos importaciones


def _storage_origen() -> Path | None:
    return Path(settings.origen_storage_dir) if settings.origen_storage_dir else None


def _huella(url: str) -> str:
    from sqlalchemy.engine import make_url
    u = make_url(url)
    return f"{u.host or 'local'}:{u.port or 5432}/{u.database}"


def _out(i: Importacion) -> dict:
    procesados = i.nuevos + i.actualizados + i.sin_cambios + i.descartados + i.omitidos + i.errores
    return {
        "id": i.id, "estado": i.estado, "iniciada_en": i.iniciada_en, "terminada_en": i.terminada_en,
        "encontrados": i.encontrados, "procesados": procesados,
        "nuevos": i.nuevos, "actualizados": i.actualizados, "sin_cambios": i.sin_cambios,
        "descartados": i.descartados, "omitidos": i.omitidos, "errores": i.errores,
        "retirados": i.retirados, "sin_evidencia": i.sin_evidencia, "mensaje": i.mensaje,
    }


def _trabajo(importacion_id: int) -> None:
    eng = engine_origen()
    try:
        ejecutar_importacion(SessionLocal, eng, importacion_id, _storage_origen(), settings.storage_path())
    finally:
        eng.dispose()


@router.post("", status_code=202, dependencies=[Depends(exigir_clave)])
def iniciar():
    """Botón «Actualizar mapas de registros»: lanza la importación en segundo plano y devuelve su id."""
    eng = engine_origen()
    if eng is None:
        raise HTTPException(400, "La conexión al proyecto original no está configurada (ORIGEN_DATABASE_URL en backend/.env).")
    try:
        with eng.connect() as con:
            con.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"No se pudo conectar al proyecto original: {str(getattr(e, 'orig', e)).strip()[:200]}")
    finally:
        eng.dispose()

    with _arranque:
        try:
            nuevo_id = crear_importacion(SessionLocal, settings.origen_nombre,
                                         _huella(settings.origen_database_url), settings.origen_storage_dir)
        except ImportacionEnCurso as e:
            raise HTTPException(409, str(e))
        threading.Thread(target=_trabajo, args=(nuevo_id,), daemon=True, name=f"importacion-{nuevo_id}").start()
    return {"id": nuevo_id}


@router.get("")
def listar(limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    q = select(Importacion).order_by(Importacion.id.desc()).limit(limit)
    return [_out(i) for i in db.scalars(q)]


@router.get("/{importacion_id}")
def detalle(importacion_id: int, db: Session = Depends(get_db)):
    i = db.get(Importacion, importacion_id)
    if not i:
        raise HTTPException(404, "Importación no encontrada.")
    return _out(i)


@router.get("/{importacion_id}/errores")
def errores(importacion_id: int, limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db)):
    """Registros que no se importaron y por qué (sin GPS, coordenadas inválidas, fallos)."""
    if not db.get(Importacion, importacion_id):
        raise HTTPException(404, "Importación no encontrada.")
    total = db.scalar(select(func.count()).select_from(ImportacionError)
                      .where(ImportacionError.importacion_id == importacion_id)) or 0
    filas = db.scalars(select(ImportacionError).where(ImportacionError.importacion_id == importacion_id)
                       .order_by(ImportacionError.id).limit(limit)).all()
    por_motivo: dict[str, int] = {}
    for motivo, n in db.execute(
        select(ImportacionError.motivo, func.count()).where(ImportacionError.importacion_id == importacion_id)
        .group_by(ImportacionError.motivo).order_by(func.count().desc())
    ):
        por_motivo[motivo] = n
    return {
        "total": total, "por_motivo": por_motivo,
        "registros": [{"origen_tipo": e.origen_tipo, "origen_id": e.origen_id, "motivo": e.motivo} for e in filas],
    }
