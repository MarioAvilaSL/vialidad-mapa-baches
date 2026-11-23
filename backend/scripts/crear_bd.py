"""Prepara la base de datos propia: crea la BD, activa PostGIS y crea las tablas.

Uso (desde la carpeta backend, con el entorno virtual activado):
    python -m scripts.crear_bd

Es seguro ejecutarlo varias veces: no borra nada.
"""
import sys

from sqlalchemy.exc import OperationalError

from app.config import settings
from app.schema_init import PostgisNoDisponible, activar_postgis, crear_base_si_falta, crear_tablas


def main() -> int:
    try:
        creada = crear_base_si_falta()
    except OperationalError as e:
        print("No se pudo conectar a PostgreSQL. Revisa DATABASE_URL en backend/.env (usuario, contraseña, puerto).")
        print(f"Detalle: {str(e.orig).strip() if e.orig else e}")
        return 1
    print("Base de datos creada." if creada else "La base de datos ya existía.")

    try:
        version = activar_postgis()
    except PostgisNoDisponible as e:
        print(f"\n{e}")
        return 2
    print(f"PostGIS activo: {version}")

    crear_tablas()
    print("Tablas listas: fuentes, importaciones, importacion_errores, baches.")
    print(f"Almacenamiento de evidencias: {settings.storage_path()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
