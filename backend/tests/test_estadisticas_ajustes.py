"""Pruebas de las estadísticas y de los ajustes compartidos (Fase 6)."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app import routing
from app.db import SessionLocal
from tests.test_mapa import LAT0, LON0, M, _foco, datos  # noqa: F401  (datos es una fixture)


@pytest.fixture(autouse=True)
def ajustes_limpios():
    with SessionLocal() as db:
        db.execute(text("DELETE FROM ajustes"))
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(text("DELETE FROM ajustes"))
        db.commit()


# ── ajustes ─────────────────────────────────────────────────────────────────
def test_ajustes_por_defecto(client):
    j = client.get("/api/ajustes").json()
    assert j["valores"] == {"eps_m": 30.0, "min_vecinos": 6, "min_baches": 8, "ancho_m": 30.0}
    assert j["defectos"] == j["valores"] and j["actualizado_en"] is None


def test_guardar_y_restablecer(client):
    nuevo = {"eps_m": 25, "min_vecinos": 4, "min_baches": 12, "ancho_m": 45}
    j = client.put("/api/ajustes", json=nuevo).json()
    assert j["valores"] == {"eps_m": 25.0, "min_vecinos": 4, "min_baches": 12, "ancho_m": 45.0} and j["actualizado_en"]
    assert client.get("/api/ajustes").json()["valores"]["min_baches"] == 12             # persiste
    j = client.put("/api/ajustes", json={**nuevo, "min_baches": 20}).json()             # se puede volver a guardar
    assert j["valores"]["min_baches"] == 20
    assert client.delete("/api/ajustes").json()["valores"]["min_baches"] == 8


@pytest.mark.parametrize("campo,valor", [("eps_m", 1), ("eps_m", 5000), ("min_vecinos", 1), ("min_baches", 1000), ("ancho_m", 2), ("ancho_m", "x")])
def test_ajustes_fuera_de_rango_se_rechazan(client, campo, valor):
    r = client.put("/api/ajustes", json={"eps_m": 30, "min_vecinos": 6, "min_baches": 8, "ancho_m": 30, campo: valor})
    assert r.status_code == 422
    assert client.get("/api/ajustes").json()["actualizado_en"] is None                   # no se guardó nada


def test_valor_dañado_en_la_bd_vuelve_a_los_de_fabrica(client):
    with SessionLocal() as db:
        db.execute(text("""INSERT INTO ajustes (clave, valor) VALUES ('general', '{"eps_m": -5}'::jsonb)"""))
        db.commit()
    assert client.get("/api/ajustes").json()["valores"]["eps_m"] == 30.0


def test_las_zonas_usan_los_ajustes_guardados_salvo_que_se_indique_otra_cosa(client, datos):
    _foco(datos, 6)                                                    # 6 baches: no llegan al mínimo de fábrica (8)
    assert client.get("/api/zonas").json()["features"] == []
    client.put("/api/ajustes", json={"eps_m": 30, "min_vecinos": 6, "min_baches": 6, "ancho_m": 30})
    z = client.get("/api/zonas").json()
    assert len(z["features"]) == 1 and z["parametros"]["min_baches"] == 6
    assert client.get("/api/zonas", params={"min_baches": 7}).json()["features"] == []   # lo explícito manda


def test_la_ruta_usa_el_ancho_guardado(client, datos, monkeypatch):
    datos(lat=LAT0, lon=LON0 + 40 * M)                                 # a ~40 m de la ruta
    monkeypatch.setattr(routing, "calcular", lambda o, d, n=3: [
        {"distancia_m": 667.0, "tiempo_s": 60.0, "coords": [[LON0, LAT0 - 0.003], [LON0, LAT0 + 0.003]]}])
    cuerpo = {"origen": {"lat": LAT0 - 0.003, "lon": LON0}, "destino": {"lat": LAT0 + 0.003, "lon": LON0}}
    assert client.post("/api/rutas/planificar", json=cuerpo).json()["rutas"][0]["resumen"]["baches"] == 0      # 30 m
    client.put("/api/ajustes", json={"eps_m": 30, "min_vecinos": 6, "min_baches": 8, "ancho_m": 60})
    j = client.post("/api/rutas/planificar", json=cuerpo).json()
    assert j["ancho_m"] == 60 and j["rutas"][0]["resumen"]["baches"] == 1


# ── estadísticas ────────────────────────────────────────────────────────────
def _fecha(y, m, d, h=12):
    return datetime(y, m, d, h, 0, tzinfo=timezone.utc)


def test_estadisticas_totales_y_series(client, datos):
    datos(severidad_nivel="alta", origen_tipo="foto", detectado_en=_fecha(2026, 3, 10), confianza=0.8, tramo_nombre="Av. Bolívar")
    datos(severidad_nivel="media", detectado_en=_fecha(2026, 3, 20), confianza=0.6, tramo_nombre="Av. Bolívar")
    datos(severidad_nivel="baja", detectado_en=_fecha(2026, 4, 2), confianza=0.4, tramo_nombre="Calle Sucre", ciudad="Machala")
    datos(severidad_nivel="alta", detectado_en=_fecha(2026, 4, 3), tramo_nombre=None, ciudad=None)
    datos(estado="descartado_origen")                                  # no cuenta
    j = client.get("/api/estadisticas").json()
    assert j["total"] == 4
    assert j["por_severidad"] == {"alta": 2, "media": 1, "baja": 1}
    assert j["por_origen"] == {"foto": 1, "video": 3}
    assert j["confianza_media"] == pytest.approx(0.6, abs=0.001)
    assert [(m["mes"], m["n"], m["alta"]) for m in j["por_mes"]] == [("2026-03", 2, 1), ("2026-04", 2, 1)]
    assert j["por_tramo"][0] == {"nombre": "Av. Bolívar", "ciudad": "Pasaje", "n": 2, "alta": 1, "media": 1, "baja": 0}
    assert [c["nombre"] for c in j["por_ciudad"]] == ["Pasaje", "Machala"] and j["sin_calle"] == 1
    assert j["fecha_min"] == "2026-03-10" and j["fecha_max"] == "2026-04-03"


def test_el_mes_se_calcula_en_hora_de_ecuador(client, datos):
    # 1 de abril 02:00 UTC = 31 de marzo 21:00 en Ecuador (UTC-5)
    datos(detectado_en=datetime(2026, 4, 1, 2, 0, tzinfo=timezone.utc))
    assert client.get("/api/estadisticas").json()["por_mes"][0]["mes"] == "2026-03"


def test_estadisticas_respetan_los_filtros(client, datos):
    datos(severidad_nivel="alta", ciudad="Pasaje")
    datos(severidad_nivel="baja", ciudad="Machala")
    assert client.get("/api/estadisticas", params={"ciudad": "Machala"}).json()["total"] == 1
    assert client.get("/api/estadisticas", params={"severidad": "alta"}).json()["por_severidad"]["baja"] == 0


def test_estadisticas_zonas_principales(client, datos):
    _foco(datos, 10, severidad_nivel="alta")
    datos(lat=LAT0 + 0.01, lon=LON0)
    z = client.get("/api/estadisticas").json()["zonas"]
    assert z["total"] == 1 and z["baches_en_zonas"] == 10 and z["parametros"]["min_baches"] == 8
    assert z["principales"][0]["n"] == 10 and z["principales"][0]["tramo"] == "Av. Bolívar"


def test_estadisticas_sin_datos(client, datos):
    j = client.get("/api/estadisticas").json()
    assert j["total"] == 0 and j["por_mes"] == [] and j["zonas"]["total"] == 0 and j["confianza_media"] is None
