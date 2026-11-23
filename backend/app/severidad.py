"""Severidad de un bache individual (0-100) y su nivel: baja, media o alta.

IMPORTANTE: es una HEURÍSTICA propia del proyecto, NO una medición de ingeniería vial ni está validada por un
experto. Se calcula con lo único que el proyecto original guarda de cada bache:

  - tamaño relativo: fracción de la imagen que ocupa la caja detectada (`area_frac`). Depende de la altura y
    el ángulo de la cámara y de la distancia al bache, así que NO es el tamaño real en centímetros;
  - confianza del modelo (probabilidad de que sea realmente un bache);
  - persistencia (solo video): en cuántos fotogramas analizados apareció el mismo bache.

Los pesos y umbrales están aquí, juntos, para poder calibrarlos con criterio experto y datos reales.
"""
import math

K_TAMANO = 15.0          # saturación del tamaño: con 5 % de la imagen el componente ya vale ~53
APARICIONES_MAX = 6      # a partir de este número de fotogramas la persistencia no suma más
PESOS_FOTO = (0.65, 0.35)            # (tamaño, confianza)
PESOS_VIDEO = (0.55, 0.30, 0.15)     # (tamaño, confianza, persistencia)
UMBRAL_MEDIA = 35.0
UMBRAL_ALTA = 60.0


def nivel(puntaje: float) -> str:
    if puntaje >= UMBRAL_ALTA:
        return "alta"
    if puntaje >= UMBRAL_MEDIA:
        return "media"
    return "baja"


def calcular(confianza: float, area_frac: float | None, n_apariciones: int | None = None) -> tuple[float, str]:
    """Devuelve (puntaje 0-100, nivel). `n_apariciones` solo existe para baches de video."""
    area = min(max(area_frac or 0.0, 0.0), 1.0)
    conf = min(max(confianza, 0.0), 1.0)
    tamano = 100.0 * (1.0 - math.exp(-K_TAMANO * area))
    if n_apariciones is None:
        w_t, w_c = PESOS_FOTO
        puntaje = w_t * tamano + w_c * 100.0 * conf
    else:
        w_t, w_c, w_p = PESOS_VIDEO
        persistencia = 100.0 * min(max(n_apariciones, 0) / APARICIONES_MAX, 1.0)
        puntaje = w_t * tamano + w_c * 100.0 * conf + w_p * persistencia
    puntaje = round(puntaje, 1)
    return puntaje, nivel(puntaje)
