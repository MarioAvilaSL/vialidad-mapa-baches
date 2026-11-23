"""Pruebas del planificador de rutas: el motor de rutas se sustituye por rutas fijas; PostGIS es real."""
import httpx
import pytest

from app import routing
from tests.test_mapa import LAT0, LON0, M, _foco, datos  # noqa: F401  (datos es una fixture)


def _ruta(puntos, distancia=None, tiempo=100.0):
    """puntos: [(lat, lon), …] → ruta con el formato del motor."""
    return {"distancia_m": distancia or 1000.0, "tiempo_s": tiempo, "coords": [[lo, la] for la, lo in puntos]}


@pytest.fixture()
def motor(monkeypatch):
    """Permite fijar las rutas que «devuelve» el motor."""
    estado = {"rutas": []}
    monkeypatch.setattr(routing, "calcular", lambda o, d, n=3: estado["rutas"])
    return estado


def _foco_a(datos, n, este_m, **kw):
    """n baches agrupados (~20 m) `este_m` metros al este de la ruta norte-sur."""
    for i in range(n):
        datos(lat=LAT0 + (i % 4) * 5 * M, lon=LON0 + (este_m + (i // 4) * 5) * M, **kw)


CUERPO = {"origen": {"lat": LAT0 - 0.003, "lon": LON0}, "destino": {"lat": LAT0 + 0.003, "lon": LON0}}
NORTE_SUR = [(LAT0 - 0.003, LON0), (LAT0 + 0.003, LON0)]                  # ~667 m
POR_EL_ESTE = [(LAT0 - 0.003, LON0), (LAT0 - 0.003, LON0 + 0.004), (LAT0 + 0.003, LON0 + 0.004), (LAT0 + 0.003, LON0)]


def test_la_ruta_lista_baches_en_orden_y_la_zona_que_cruza(client, datos, motor):
    _foco(datos, 12, severidad_nivel="alta")                      # foco justo sobre la ruta
    datos(lat=LAT0 + 0.0025, lon=LON0 + 5 * M, severidad_nivel="media")   # un bache suelto al norte, a 5 m
    datos(lat=LAT0, lon=LON0 + 0.01)                              # lejos de la ruta: no cuenta
    datos(lat=LAT0, lon=LON0, estado="descartado_origen")        # no activo: no cuenta
    motor["rutas"] = [_ruta(NORTE_SUR, 667, 60)]
    j = client.post("/api/rutas/planificar", json=CUERPO).json()
    r = j["rutas"][0]
    assert r["resumen"]["baches"] == 13 and r["resumen"]["alta"] == 12 and r["resumen"]["media"] == 1
    assert r["resumen"]["riesgo"] == 12 * 3 + 2
    assert [b["desde_m"] for b in r["baches"]] == sorted(b["desde_m"] for b in r["baches"])
    assert r["baches"][-1]["severidad"] == "media" and r["baches"][-1]["desde_m"] > 600
    assert len(r["zonas"]) == 1
    z = r["zonas"][0]
    assert z["n"] == 12 and z["cruza"] is True and z["geometry"]["type"] == "Polygon"
    # el foco está a ~330 m del origen: se entra en la zona un poco antes de esa distancia
    assert 280 < z["desde_m"] < 340
    assert j["recomendada"] == 0 and j["mas_rapida"] == 0


def test_una_zona_cercana_pero_no_cruzada_se_informa_sin_cruzar(client, datos, motor):
    _foco_a(datos, 12, 30)                                    # foco a 20 m de la ruta
    motor["rutas"] = [_ruta(NORTE_SUR)]
    r = client.post("/api/rutas/planificar", json={**CUERPO, "ancho_m": 40}).json()["rutas"][0]
    assert len(r["zonas"]) == 1 and r["zonas"][0]["cruza"] is False and 0 < r["zonas"][0]["lateral_m"] < 40
    sin = client.post("/api/rutas/planificar", json={**CUERPO, "ancho_m": 5}).json()["rutas"][0]
    assert sin["zonas"] == []


def test_recomienda_la_ruta_con_menos_riesgo_si_no_tarda_demasiado(client, datos, motor):
    _foco(datos, 12, severidad_nivel="alta")
    motor["rutas"] = [_ruta(NORTE_SUR, 667, 60), _ruta(POR_EL_ESTE, 1500, 75)]     # la 2.ª tarda 1,25 ×
    j = client.post("/api/rutas/planificar", json=CUERPO).json()
    assert j["mas_rapida"] == 0 and j["recomendada"] == 1
    assert j["rutas"][0]["resumen"]["riesgo"] > 0 and j["rutas"][1]["resumen"]["riesgo"] == 0


def test_no_recomienda_un_rodeo_demasiado_largo(client, datos, motor):
    _foco(datos, 12, severidad_nivel="alta")
    motor["rutas"] = [_ruta(NORTE_SUR, 667, 60), _ruta(POR_EL_ESTE, 3000, 200)]    # 3,3 ×
    j = client.post("/api/rutas/planificar", json=CUERPO).json()
    assert j["recomendada"] == 0


def test_errores_del_motor_llegan_con_su_codigo(client, datos, monkeypatch):
    def falla(*a, **k):
        raise routing.RutasError("sin motor", 503)
    monkeypatch.setattr(routing, "calcular", falla)
    r = client.post("/api/rutas/planificar", json=CUERPO)
    assert r.status_code == 503 and r.json()["detail"] == "sin motor"


def test_validaciones(client, datos):
    p = {"lat": LAT0, "lon": LON0}
    assert client.post("/api/rutas/planificar", json={"origen": p, "destino": p}).status_code == 422
    assert client.post("/api/rutas/planificar", json={"origen": {"lat": 99, "lon": 0}, "destino": p}).status_code == 422
    assert client.post("/api/rutas/planificar", json={**CUERPO, "ancho_m": 1}).status_code == 422


def test_sin_baches_la_ruta_sale_limpia(client, datos, motor):
    motor["rutas"] = [_ruta(NORTE_SUR)]
    r = client.post("/api/rutas/planificar", json=CUERPO).json()["rutas"][0]
    assert r["baches"] == [] and r["zonas"] == [] and r["resumen"]["riesgo"] == 0


def test_el_estado_del_motor_aparece_en_health(client, monkeypatch):
    monkeypatch.setattr(routing, "estado", lambda: {"configurado": True, "disponible": False, "detalle": "x"})
    assert client.get("/api/health").json()["rutas"] == {"configurado": True, "disponible": False, "detalle": "x"}
    assert client.get("/api/rutas/estado").json()["disponible"] is False


# ── cliente del motor (sin red: se sustituye la petición HTTP) ───────────────
def _resp(codigo, cuerpo):
    return httpx.Response(codigo, json=cuerpo, request=httpx.Request("GET", "http://x/route"))


def _paths(n):
    return {"paths": [{"distance": 1000.0 + i, "time": 60000 + i, "points": {"type": "LineString",
            "coordinates": [[-79.95, -3.26], [-79.94, -3.25]]}} for i in range(n)]}


def test_cliente_interpreta_las_rutas(monkeypatch):
    visto = {}
    monkeypatch.setattr(routing, "_pedir", lambda params: visto.setdefault("p", params) and _resp(200, _paths(2)))
    r = routing.calcular((-3.26, -79.95), (-3.25, -79.94), 3)
    assert len(r) == 2 and r[0]["tiempo_s"] == 60.0 and r[0]["coords"][0] == [-79.95, -3.26]
    assert ("algorithm", "alternative_route") in visto["p"] and ("point", "-3.26,-79.95") in visto["p"]


def test_cliente_se_adapta_si_el_motor_no_admite_alternativas(monkeypatch):
    llamadas = []

    def pedir(params):
        llamadas.append(params)
        if ("algorithm", "alternative_route") in params:
            return _resp(400, {"message": "Alternative paths not supported with CH"})
        return _resp(200, _paths(1))
    monkeypatch.setattr(routing, "_pedir", pedir)
    assert len(routing.calcular((0, 0), (1, 1), 3)) == 1 and len(llamadas) == 2


@pytest.mark.parametrize("codigo,mensaje,esperado", [
    (400, "Point 1 is out of bounds: -10.0,-79.0", 422),
    (400, "Cannot find point 0: 1.0,2.0", 422),
    (400, "Connection between locations not found", 422),
    (500, "boom", 502),
])
def test_cliente_traduce_errores(monkeypatch, codigo, mensaje, esperado):
    monkeypatch.setattr(routing, "_pedir", lambda params: _resp(codigo, {"message": mensaje}))
    with pytest.raises(routing.RutasError) as e:
        routing.calcular((0, 0), (1, 1), 1)
    assert e.value.status == esperado


def test_cliente_motor_apagado(monkeypatch):
    def refusa(*a, **k):
        raise httpx.ConnectError("no")
    monkeypatch.setattr(httpx, "get", refusa)
    with pytest.raises(routing.RutasError) as e:
        routing.calcular((0, 0), (1, 1), 1)
    assert e.value.status == 503
    assert routing.estado()["disponible"] is False
