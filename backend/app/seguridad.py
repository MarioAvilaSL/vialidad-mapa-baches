"""Clave de acceso opcional para las operaciones que modifican datos.

Si `API_TOKEN` está definida en `.env`, importar y cambiar los ajustes compartidos exigen la cabecera `X-Clave`.
Consultar el mapa, las estadísticas y las rutas no la exige. Pensada para cuando el servidor se alcanza desde el
celular por la red: evita que cualquier equipo de la red cambie los ajustes o lance importaciones. No sustituye a
https: la clave viaja en claro por la red local.
"""
import secrets

from fastapi import Header, HTTPException

from .config import settings


def requiere_clave() -> bool:
    return bool(settings.api_token)


def clave_valida(clave: str | None) -> bool:
    return not requiere_clave() or (clave is not None and secrets.compare_digest(clave, settings.api_token))


def exigir_clave(x_clave: str | None = Header(None, alias="X-Clave")) -> None:
    if not clave_valida(x_clave):
        raise HTTPException(401, "Falta la clave de acceso o es incorrecta (ver Ajustes → Conexión).")
