"""Clave de acceso opcional y orígenes CORS de la app Android."""
import pytest

from app.config import settings


@pytest.fixture()
def con_clave(monkeypatch):
    monkeypatch.setattr(settings, "api_token", "secreta")


AJ = {"eps_m": 30, "min_vecinos": 6, "min_baches": 8, "ancho_m": 30}


def test_sin_clave_configurada_todo_funciona_como_antes(client):
    assert client.get("/api/acceso").json() == {"requiere_clave": False, "clave_valida": True}
    assert client.put("/api/ajustes", json=AJ).status_code == 200
    assert client.delete("/api/ajustes").status_code == 200


def test_con_clave_las_escrituras_la_exigen(client, con_clave):
    assert client.put("/api/ajustes", json=AJ).status_code == 401
    assert client.put("/api/ajustes", json=AJ, headers={"X-Clave": "mala"}).status_code == 401
    assert client.delete("/api/ajustes").status_code == 401
    assert client.post("/api/importaciones").status_code == 401
    assert client.put("/api/ajustes", json=AJ, headers={"X-Clave": "secreta"}).status_code == 200
    assert client.delete("/api/ajustes", headers={"X-Clave": "secreta"}).status_code == 200


def test_con_clave_la_lectura_sigue_abierta(client, con_clave):
    for ruta in ("/api/baches", "/api/zonas", "/api/estadisticas", "/api/ajustes", "/api/health", "/api/resumen"):
        assert client.get(ruta).status_code == 200, ruta


def test_acceso_informa_si_la_clave_es_correcta(client, con_clave):
    assert client.get("/api/acceso").json() == {"requiere_clave": True, "clave_valida": False}
    assert client.get("/api/acceso", headers={"X-Clave": "mala"}).json()["clave_valida"] is False
    assert client.get("/api/acceso", headers={"X-Clave": "secreta"}).json()["clave_valida"] is True


@pytest.mark.parametrize("origen", ["https://localhost", "http://localhost", "capacitor://localhost", "http://localhost:5173"])
def test_cors_permite_la_app(client, origen):
    r = client.options("/api/ajustes", headers={"Origin": origen, "Access-Control-Request-Method": "PUT",
                                                 "Access-Control-Request-Headers": "x-clave,content-type"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == origen


def test_cors_rechaza_otros_origenes(client):
    r = client.options("/api/ajustes", headers={"Origin": "https://sitio-ajeno.example", "Access-Control-Request-Method": "PUT"})
    assert "access-control-allow-origin" not in r.headers
