"""Cliente del motor de rutas GraphHopper (código abierto, corre en el propio equipo; ver graphhopper/README.md)."""
import httpx

from .config import settings


class RutasError(Exception):
    """Error al pedir una ruta; `status` es el código HTTP que se devuelve a la interfaz."""

    def __init__(self, mensaje: str, status: int = 502):
        super().__init__(mensaje)
        self.mensaje, self.status = mensaje, status


def estado() -> dict:
    """¿Está el motor de rutas en marcha? (para el panel de estado)."""
    if not settings.routing_url:
        return {"configurado": False, "disponible": False, "detalle": "ROUTING_URL no está configurada."}
    try:
        r = httpx.get(f"{settings.routing_url.rstrip('/')}/health", timeout=2.0)
        if r.status_code == 200:
            return {"configurado": True, "disponible": True, "detalle": None}
        return {"configurado": True, "disponible": False, "detalle": f"respondió {r.status_code}"}
    except httpx.HTTPError:
        return {"configurado": True, "disponible": False,
                "detalle": "no responde: ¿está arrancado GraphHopper? (ver graphhopper/README.md)"}


def _pedir(params: list[tuple[str, str]]) -> httpx.Response:
    try:
        return httpx.get(f"{settings.routing_url.rstrip('/')}/route", params=params, timeout=settings.routing_timeout_s)
    except httpx.HTTPError as e:
        raise RutasError("El motor de rutas no responde. Arranca GraphHopper (ver graphhopper/README.md).", 503) from e


def _mensaje(r: httpx.Response) -> str:
    try:
        return str(r.json().get("message") or r.text)[:300]
    except ValueError:
        return r.text[:300]


def calcular(origen: tuple[float, float], destino: tuple[float, float], alternativas: int = 3) -> list[dict]:
    """Rutas en coche de `origen` a `destino` (lat, lon). Devuelve [{distancia_m, tiempo_s, coords: [[lon, lat], …]}]."""
    base = [("point", f"{origen[0]},{origen[1]}"), ("point", f"{destino[0]},{destino[1]}"),
            ("profile", settings.routing_profile), ("points_encoded", "false"), ("instructions", "false"),
            ("locale", "es")]
    r = None
    if alternativas > 1:
        r = _pedir(base + [("algorithm", "alternative_route"), ("alternative_route.max_paths", str(alternativas))])
        if r.status_code == 400 and "alternative" in _mensaje(r).lower():
            r = None           # el motor no admite alternativas con su configuración: se pide solo la mejor ruta
    if r is None:
        r = _pedir(base)
    if r.status_code != 200:
        msg = _mensaje(r)
        if r.status_code == 400:
            if "out of bounds" in msg.lower() or "cannot find point" in msg.lower():
                raise RutasError("El origen o el destino está fuera del mapa cargado en el motor de rutas, "
                                 "o no hay una calle cercana.", 422)
            if "connection between locations not found" in msg.lower():
                raise RutasError("No hay camino entre el origen y el destino.", 422)
            raise RutasError(f"El motor de rutas rechazó la consulta: {msg}", 422)
        raise RutasError(f"El motor de rutas falló ({r.status_code}): {msg}", 502)
    rutas = []
    for p in r.json().get("paths", []):
        coords = p["points"]["coordinates"]
        if len(coords) >= 2:
            rutas.append({"distancia_m": float(p["distance"]), "tiempo_s": float(p["time"]) / 1000.0,
                          "coords": [[c[0], c[1]] for c in coords]})
    if not rutas:
        raise RutasError("El motor de rutas no devolvió ninguna ruta.", 502)
    return rutas
