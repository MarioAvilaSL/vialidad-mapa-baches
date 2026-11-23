"""Pruebas de la API del mapa (GeoJSON, filtros, detalle y zonas críticas)."""
from datetime import datetime, timezone

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import text

from app.db import SessionLocal
from app.models import Bache, Fuente

LAT0, LON0 = -3.2650, -79.9550
M = 1 / 111_320      # un metro en grados de latitud (en longitud cerca del ecuador es casi igual)


@pytest.fixture()
def datos():
    """Tabla limpia y una fuente; devuelve una función para añadir baches."""
    with SessionLocal() as db:
        db.execute(text("TRUNCATE importacion_errores, baches, importaciones, fuentes RESTART IDENTITY CASCADE"))
        f = Fuente(nombre="t")
        db.add(f)
        db.commit()
        fid = f.id
    contador = {"n": 0}

    def añadir(lat=LAT0, lon=LON0, **kw):
        contador["n"] += 1
        d = dict(fuente_id=fid, origen_tipo="video", origen_id=contador["n"], hash_contenido="x" * 64,
                 geom=WKTElement(f"POINT({lon} {lat})", srid=4326), gps_origen="gpx", confianza=0.6,
                 detectado_en=datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc), severidad_nivel="media",
                 severidad_puntaje=50.0, ciudad="Pasaje", tramo_nombre="Av. Bolívar", ruta_evidencia=None)
        d.update(kw)
        with SessionLocal() as db:
            b = Bache(**d)
            db.add(b)
            db.commit()
            return b.id

    return añadir


def test_geojson_con_coordenadas_lon_lat_y_solo_activos(client, datos):
    a = datos(lat=-3.2, lon=-79.8)
    datos(estado="descartado_origen")
    datos(estado="retirado_origen")
    j = client.get("/api/baches").json()
    assert j["type"] == "FeatureCollection" and j["total"] == 1 and j["truncado"] is False
    f = j["features"][0]
    assert f["geometry"] == {"type": "Point", "coordinates": [-79.8, -3.2]}      # GeoJSON: [lon, lat]
    assert f["properties"]["id"] == a and f["properties"]["severidad"] == "media"


def test_filtros_de_confianza_severidad_origen_y_ubicacion(client, datos):
    datos(confianza=0.2, severidad_nivel="baja", origen_tipo="foto", ciudad="Machala", tramo_nombre="Calle Sucre")
    datos(confianza=0.5, severidad_nivel="media")
    datos(confianza=0.9, severidad_nivel="alta")

    def n(**q):
        return client.get("/api/baches", params=q).json()["total"]

    assert n() == 3
    assert n(confianza_min=0.5) == 2
    assert n(severidad=["alta", "baja"]) == 2 and n(severidad="alta") == 1
    assert n(origen="foto") == 1
    assert n(ciudad="Machala") == 1 and n(tramo="Av. Bolívar") == 2
    assert n(ciudad="Machala", severidad="alta") == 0                              # los filtros se combinan (AND)
    assert client.get("/api/baches", params={"severidad": "extrema"}).status_code == 422
    assert client.get("/api/baches", params={"confianza_min": 2}).status_code == 422


def test_el_filtro_de_fecha_usa_la_hora_de_ecuador_no_utc(client, datos):
    # 01:00 UTC del 1 de marzo = 20:00 del 28 de febrero en Ecuador (UTC-5)
    datos(detectado_en=datetime(2026, 3, 1, 1, 0, tzinfo=timezone.utc))
    n = lambda **q: client.get("/api/baches", params=q).json()["total"]
    assert n(hasta="2026-02-28") == 1            # para el usuario es del 28
    assert n(desde="2026-03-01") == 0
    assert n(desde="2026-02-28", hasta="2026-02-28") == 1                          # los límites son inclusivos
    f = client.get("/api/baches/filtros").json()
    assert f["fecha_min"] == "2026-02-28" and f["fecha_max"] == "2026-02-28"


def test_limite_devuelve_los_mas_severos_y_avisa_que_trunco(client, datos):
    datos(severidad_puntaje=10.0, severidad_nivel="baja")
    alto = datos(severidad_puntaje=90.0, severidad_nivel="alta")
    datos(severidad_puntaje=50.0)
    j = client.get("/api/baches", params={"limit": 2}).json()
    assert j["total"] == 3 and j["truncado"] is True and len(j["features"]) == 2
    assert j["features"][0]["properties"]["id"] == alto


def test_opciones_de_filtros(client, datos):
    datos(ciudad="Pasaje", tramo_nombre="A")
    datos(ciudad="Pasaje", tramo_nombre="A")
    datos(ciudad="Machala", tramo_nombre="B")
    datos(estado="descartado_origen", ciudad="Zeta")                               # no debe aparecer
    f = client.get("/api/baches/filtros").json()
    assert f["total"] == 3
    assert {c["nombre"]: c["n"] for c in f["ciudades"]} == {"Machala": 1, "Pasaje": 2}
    assert {t["nombre"] for t in f["tramos"]} == {"A", "B"}


def test_detalle_de_un_bache(client, datos):
    i = datos(ruta_evidencia="evidencias/video/1.jpg", rumbo_grados=45.0, area_frac=0.03, n_apariciones=4)
    d = client.get(f"/api/baches/{i}").json()
    assert d["lat"] == pytest.approx(LAT0) and d["lon"] == pytest.approx(LON0)
    assert d["evidencia_url"] == "/media/evidencias/video/1.jpg"
    assert d["severidad"] == {"nivel": "media", "puntaje": 50.0} and d["rumbo_grados"] == 45.0
    assert d["origen"]["tipo"] == "video"
    sin = datos()
    assert client.get(f"/api/baches/{sin}").json()["evidencia_url"] is None
    assert client.get("/api/baches/99999").status_code == 404


def _foco(datos, n, **kw):
    """n baches dentro de ~20 m alrededor del punto base."""
    for i in range(n):
        datos(lat=LAT0 + (i % 4) * 5 * M, lon=LON0 + (i // 4) * 5 * M, **kw)


def test_zona_critica_agrupa_un_foco_y_deja_fuera_los_aislados(client, datos):
    _foco(datos, 6, severidad_nivel="alta")
    datos(lat=LAT0 + 0.01, lon=LON0)                    # a ~1,1 km
    datos(lat=LAT0, lon=LON0 + 0.01)
    z = client.get("/api/zonas", params={"eps_m": 30, "min_vecinos": 6, "min_baches": 6}).json()
    assert z["parametros"] == {"eps_m": 30, "min_vecinos": 6, "min_baches": 6}
    assert len(z["features"]) == 1
    p = z["features"][0]["properties"]
    assert p["n"] == 6 and p["alta"] == 6 and p["tramo"] == "Av. Bolívar" and p["ciudad"] == "Pasaje"
    assert p["registros"] >= 1
    assert z["features"][0]["geometry"]["type"] == "Polygon"
    assert p["lat"] == pytest.approx(LAT0, abs=0.001) and p["lon"] == pytest.approx(LON0, abs=0.001)


def test_valores_por_defecto_exigen_densidad(client, datos):
    _foco(datos, 6)
    assert client.get("/api/zonas").json()["features"] == []          # 6 < min_baches por defecto (8)
    _foco(datos, 4)
    assert len(client.get("/api/zonas").json()["features"]) == 1      # 10 baches juntos sí


def test_baches_en_fila_no_forman_zona_con_densidad_pero_si_con_encadenamiento(client, datos):
    """8 baches en fila cada 30 m: ninguno tiene 6 vecinos cerca (no es concentración), pero encadenados sí se unen."""
    for i in range(8):
        datos(lat=LAT0 + i * 30 * M, lon=LON0, severidad_nivel="media" if i % 2 else "alta")
    assert client.get("/api/zonas", params={"eps_m": 50, "min_vecinos": 6, "min_baches": 5}).json()["features"] == []
    z = client.get("/api/zonas", params={"eps_m": 50, "min_vecinos": 2, "min_baches": 5}).json()["features"]
    assert len(z) == 1 and z[0]["properties"]["n"] == 8
    assert z[0]["properties"]["alta"] == 4 and z[0]["properties"]["media"] == 4
    assert client.get("/api/zonas", params={"eps_m": 50, "min_vecinos": 2, "min_baches": 9}).json()["features"] == []
    assert client.get("/api/zonas", params={"eps_m": 20, "min_vecinos": 2, "min_baches": 2}).json()["features"] == []


def test_zona_respeta_distancia_y_minimo(client, datos):
    _foco(datos, 6)
    assert len(client.get("/api/zonas", params={"min_baches": 7}).json()["features"]) == 0
    # separados por 100 m entre sí: con eps=50 no forman zona, con eps=150 sí
    for i in range(6):
        datos(lat=LAT0 + 0.03 + i * 100 * M, lon=LON0)
    q = {"min_vecinos": 2, "min_baches": 5}
    cerca = client.get("/api/zonas", params={**q, "eps_m": 50}).json()["features"]
    lejos = client.get("/api/zonas", params={**q, "eps_m": 150}).json()["features"]
    assert len(cerca) == 1 and len(lejos) == 2


def test_zona_cuenta_registros_de_origen_distintos(client, datos):
    _foco(datos, 8, origen_padre_id=1)
    for _ in range(2):
        datos(lat=LAT0, lon=LON0, origen_padre_id=2)
    p = client.get("/api/zonas", params={"eps_m": 30, "min_vecinos": 6, "min_baches": 8}).json()["features"][0]["properties"]
    assert p["n"] == 10 and p["registros"] == 2


def test_las_zonas_respetan_los_filtros(client, datos):
    _foco(datos, 9, severidad_nivel="alta", ciudad="Pasaje")
    assert len(client.get("/api/zonas", params={"severidad": "alta"}).json()["features"]) == 1
    assert len(client.get("/api/zonas", params={"severidad": "baja"}).json()["features"]) == 0
    assert len(client.get("/api/zonas", params={"ciudad": "Machala"}).json()["features"]) == 0


def test_zonas_sin_datos_no_falla(client, datos):
    j = client.get("/api/zonas").json()
    assert j["features"] == []
