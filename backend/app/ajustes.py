"""Ajustes persistentes compartidos (zonas críticas y ancho del corredor de las rutas).

Se guardan en la base de datos para que la web y la app Android usen los mismos valores. Los ajustes propios de cada
dispositivo (voz, tono, distancia de aviso) se guardan en el dispositivo.
"""
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from .models import Ajuste

CLAVE = "general"
DEFECTO = {"eps_m": 30.0, "min_vecinos": 6, "min_baches": 8, "ancho_m": 30.0}


class AjustesIn(BaseModel):
    eps_m: float = Field(DEFECTO["eps_m"], ge=5, le=1000, description="Zonas críticas: cercanía entre baches vecinos (m)")
    min_vecinos: int = Field(DEFECTO["min_vecinos"], ge=2, le=50, description="Zonas críticas: baches cerca que necesita cada bache")
    min_baches: int = Field(DEFECTO["min_baches"], ge=2, le=500, description="Zonas críticas: tamaño mínimo de una zona")
    ancho_m: float = Field(DEFECTO["ancho_m"], ge=5, le=100, description="Rutas: distancia máxima de un bache al eje de la ruta (m)")


def leer(db: Session) -> dict:
    """Valores vigentes: los guardados o, si faltan o están dañados, los de fábrica."""
    fila = db.get(Ajuste, CLAVE)
    try:
        return AjustesIn(**{**DEFECTO, **(fila.valor if fila else {})}).model_dump()
    except (ValidationError, TypeError):
        return dict(DEFECTO)


def actualizado_en(db: Session):
    fila = db.get(Ajuste, CLAVE)
    return fila.actualizado_en if fila else None


def guardar(db: Session, a: AjustesIn) -> dict:
    fila = db.get(Ajuste, CLAVE)
    if fila:
        fila.valor = a.model_dump()
    else:
        db.add(Ajuste(clave=CLAVE, valor=a.model_dump()))
    db.commit()
    return leer(db)


def restablecer(db: Session) -> dict:
    fila = db.get(Ajuste, CLAVE)
    if fila:
        db.delete(fila)
        db.commit()
    return leer(db)
