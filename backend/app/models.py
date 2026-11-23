"""Modelo de datos propio del mapa de baches (PostgreSQL + PostGIS).

Cada bache importado conserva la identidad de su registro en el proyecto original
(fuente + tipo de origen + id de origen), por lo que reimportar nunca crea duplicados
y siempre se puede rastrear de dónde salió cada dato.
"""
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

ORIGENES = ("foto", "video")
ESTADOS = ("activo", "descartado_origen", "retirado_origen")
GPS_ORIGENES = ("exif", "manual", "gpx")
SEVERIDADES = ("baja", "media", "alta")


class Fuente(Base):
    """Una instalación del proyecto original de la que se importan baches."""

    __tablename__ = "fuentes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    tipo: Mapped[str] = mapped_column(String(30), default="vialidad_yolo", server_default="vialidad_yolo")
    huella: Mapped[str | None] = mapped_column(String(80))      # identifica la BD de origen (se fija en la Fase 3)
    storage_dir: Mapped[str | None] = mapped_column(Text)       # carpeta storage/ del proyecto original
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    importaciones: Mapped[list["Importacion"]] = relationship(back_populates="fuente")


class Importacion(Base):
    """Una ejecución del botón «Actualizar mapas de registros» y su resumen."""

    __tablename__ = "importaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    fuente_id: Mapped[int] = mapped_column(ForeignKey("fuentes.id", ondelete="RESTRICT"), index=True)
    iniciada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(String(12), default="en_curso", server_default="en_curso")  # en_curso | completada | fallida
    # Cada bache encontrado en el origen cae en EXACTAMENTE una de estas categorías:
    # encontrados = nuevos + actualizados + sin_cambios + descartados + omitidos + errores
    encontrados: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    nuevos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    actualizados: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sin_cambios: Mapped[int] = mapped_column(Integer, default=0, server_default="0")   # los «duplicados»: ya estaban importados
    descartados: Mapped[int] = mapped_column(Integer, default=0, server_default="0")   # descartados a mano en el origen
    omitidos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")      # sin coordenadas GPS válidas
    errores: Mapped[int] = mapped_column(Integer, default=0, server_default="0")       # fallo inesperado al procesarlos
    # Aparte: no forman parte de «encontrados»
    retirados: Mapped[int] = mapped_column(Integer, default=0, server_default="0")     # importados antes y ya inexistentes en el origen
    sin_evidencia: Mapped[int] = mapped_column(Integer, default=0, server_default="0") # importados sin poder copiar la imagen
    mensaje: Mapped[str | None] = mapped_column(Text)                                  # motivo si la importación falló

    fuente: Mapped[Fuente] = relationship(back_populates="importaciones")
    detalle_errores: Mapped[list["ImportacionError"]] = relationship(
        back_populates="importacion", cascade="all, delete-orphan", passive_deletes=True
    )


class ImportacionError(Base):
    """Registro de origen que no se pudo importar y el motivo (sin coordenadas, imagen faltante, etc.)."""

    __tablename__ = "importacion_errores"

    id: Mapped[int] = mapped_column(primary_key=True)
    importacion_id: Mapped[int] = mapped_column(ForeignKey("importaciones.id", ondelete="CASCADE"), index=True)
    origen_tipo: Mapped[str] = mapped_column(String(10))
    origen_id: Mapped[int] = mapped_column(BigInteger)
    motivo: Mapped[str] = mapped_column(String(200))

    importacion: Mapped[Importacion] = relationship(back_populates="detalle_errores")


class Bache(Base):
    """Un bache importado. Solo existen registros de la clase `pothole`; nada más se importa."""

    __tablename__ = "baches"
    __table_args__ = (
        UniqueConstraint("fuente_id", "origen_tipo", "origen_id", name="uq_bache_origen"),
        CheckConstraint("origen_tipo IN ('foto','video')", name="ck_bache_origen_tipo"),
        CheckConstraint("estado IN ('activo','descartado_origen','retirado_origen')", name="ck_bache_estado"),
        CheckConstraint("confianza >= 0 AND confianza <= 1", name="ck_bache_confianza"),
        Index("ix_baches_geom", "geom", postgresql_using="gist"),
        Index("ix_baches_estado_fecha", "estado", "detectado_en"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Identidad y trazabilidad (de dónde viene)
    fuente_id: Mapped[int] = mapped_column(ForeignKey("fuentes.id", ondelete="RESTRICT"))
    origen_tipo: Mapped[str] = mapped_column(String(10))        # foto | video
    origen_id: Mapped[int] = mapped_column(BigInteger)          # detecciones.id (foto) o video_hallazgos.id (video)
    origen_padre_id: Mapped[int | None] = mapped_column(BigInteger)  # capturas.id o videos.id
    hash_contenido: Mapped[str] = mapped_column(String(64))     # detecta cambios en el origen entre importaciones
    importacion_id: Mapped[int | None] = mapped_column(ForeignKey("importaciones.id", ondelete="SET NULL"))

    # Ubicación (aproximada: es la posición de la cámara, no la del bache)
    geom = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    gps_origen: Mapped[str] = mapped_column(String(10))         # exif | manual | gpx
    rumbo_grados: Mapped[float | None] = mapped_column(Float)   # solo cuando se puede deducir de la ruta GPX

    # Detección
    detectado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confianza: Mapped[float] = mapped_column(Float)
    area_frac: Mapped[float | None] = mapped_column(Float)     # fracción de la imagen que ocupa (foto: caja; video: máximo)
    n_apariciones: Mapped[int | None] = mapped_column(Integer)  # solo video: fotogramas donde se vio
    modelo_version: Mapped[str | None] = mapped_column(String(80))
    perfil: Mapped[str | None] = mapped_column(String(10))
    parametros: Mapped[dict | None] = mapped_column(JSONB)

    # Severidad (heurística propia, se calcula al importar y se puede recalcular)
    severidad_nivel: Mapped[str | None] = mapped_column(String(8))
    severidad_puntaje: Mapped[float | None] = mapped_column(Float)

    # Contexto copiado del origen
    tramo_nombre: Mapped[str | None] = mapped_column(String(120))
    ciudad: Mapped[str | None] = mapped_column(String(80))

    # Evidencia (copia propia, para no depender de que el origen conserve el archivo)
    ruta_evidencia: Mapped[str | None] = mapped_column(String(255))
    evidencia_sha256: Mapped[str | None] = mapped_column(String(64))

    estado: Mapped[str] = mapped_column(String(20), default="activo", server_default="activo")
    importado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Ajuste(Base):
    """Ajustes compartidos por la web y Android (guardados en el servidor). Una sola fila, clave «general»."""

    __tablename__ = "ajustes"

    clave: Mapped[str] = mapped_column(String(40), primary_key=True)
    valor: Mapped[dict] = mapped_column(JSONB)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
