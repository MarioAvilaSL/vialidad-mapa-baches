"""Ajustes compartidos (se aplican por defecto en el mapa, la conducción y el planificador de rutas)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import ajustes as aj
from ..db import get_db
from ..seguridad import exigir_clave

router = APIRouter(prefix="/api/ajustes", tags=["ajustes"])


def _respuesta(db: Session, valores: dict):
    return {"valores": valores, "defectos": aj.DEFECTO, "actualizado_en": aj.actualizado_en(db)}


@router.get("")
def leer_ajustes(db: Session = Depends(get_db)):
    return _respuesta(db, aj.leer(db))


@router.put("", dependencies=[Depends(exigir_clave)])
def guardar_ajustes(datos: aj.AjustesIn, db: Session = Depends(get_db)):
    """Guarda los ajustes (todos a la vez). Valores fuera de rango se rechazan."""
    return _respuesta(db, aj.guardar(db, datos))


@router.delete("", dependencies=[Depends(exigir_clave)])
def restablecer_ajustes(db: Session = Depends(get_db)):
    """Vuelve a los valores de fábrica."""
    return _respuesta(db, aj.restablecer(db))
