import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from . import schema_init
from .config import settings
from .db import SessionLocal
from .importador import marcar_interrumpidas
from .routers import ajustes, baches, estadisticas, estado, importaciones, rutas

log = logging.getLogger("vialidad_mapa")
STORAGE = settings.storage_path()
STORAGE.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # La estructura de la BD se crea con `python -m scripts.crear_bd`. Aquí solo se añaden tablas y columnas nuevas de fases
    # posteriores y se cierran importaciones que quedaron «en curso» por un reinicio.
    try:
        schema_init.crear_tablas()          # crea las tablas nuevas que falten y añade columnas nuevas (no borra nada)
        n = marcar_interrumpidas(SessionLocal)
        if n:
            log.warning("%s importación(es) interrumpida(s) por un reinicio, marcadas como fallidas.", n)
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo preparar la base de datos al arrancar: %s", e)
    log.info("Vialidad Mapa iniciado. Almacenamiento: %s", STORAGE)
    yield


app = FastAPI(title="Vialidad Mapa · Baches", version="0.1.0", lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1000)   # el GeoJSON de cientos de baches se comprime mucho
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list(),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.include_router(estado.router)
app.include_router(importaciones.router)
app.include_router(baches.router)
app.include_router(rutas.router)
app.include_router(ajustes.router)
app.include_router(estadisticas.router)
app.mount("/media", StaticFiles(directory=STORAGE), name="media")
