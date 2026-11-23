"""Preparación de la BD propia: crea la base si no existe, activa PostGIS y crea las tablas."""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from .config import settings
from .db import Base, engine
from . import models  # noqa: F401  (registra las tablas en Base.metadata)

MENSAJE_POSTGIS = (
    "PostGIS no está instalado en este PostgreSQL. En Windows: abre «Application Stack Builder» (menú Inicio, "
    "carpeta PostgreSQL 16), elige tu servidor, abre «Spatial Extensions», marca «PostGIS 3.x Bundle for PostgreSQL 16» "
    "e instálalo (puedes aceptar las opciones por defecto). Luego vuelve a ejecutar este comando."
)


class PostgisNoDisponible(RuntimeError):
    pass


def crear_base_si_falta() -> bool:
    """Crea la base indicada en DATABASE_URL si no existe. Devuelve True si la creó."""
    url = make_url(settings.database_url)
    nombre = url.database
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as con:
            existe = con.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": nombre})
            if existe:
                return False
            con.execute(text(f'CREATE DATABASE "{nombre}"'))
            return True
    finally:
        admin.dispose()


def activar_postgis() -> str:
    """Activa la extensión PostGIS y devuelve su versión."""
    try:
        with engine.begin() as con:
            con.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            return con.scalar(text("SELECT postgis_version()"))
    except DBAPIError as e:
        if "postgis" in str(e).lower():
            raise PostgisNoDisponible(MENSAJE_POSTGIS) from e
        raise


# Columnas añadidas después de la Fase 2 (create_all no modifica tablas ya existentes).
COLUMNAS_NUEVAS = {
    "importaciones": [
        "omitidos INTEGER NOT NULL DEFAULT 0",
        "retirados INTEGER NOT NULL DEFAULT 0",
        "sin_evidencia INTEGER NOT NULL DEFAULT 0",
        "mensaje TEXT",
    ],
}


def asegurar_columnas() -> None:
    """Añade a las tablas existentes las columnas introducidas en fases posteriores. Se puede repetir sin riesgo."""
    insp = inspect(engine)
    with engine.begin() as con:
        for tabla, cols in COLUMNAS_NUEVAS.items():
            if not insp.has_table(tabla):
                continue
            for col in cols:
                con.execute(text(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {col}"))


def crear_tablas() -> None:
    Base.metadata.create_all(engine)
    asegurar_columnas()
