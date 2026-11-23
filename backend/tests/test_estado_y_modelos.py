from datetime import datetime, timezone

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models import Bache, Fuente


def _fuente(db):
    f = Fuente(nombre=f"test-{datetime.now().timestamp()}")
    db.add(f)
    db.flush()
    return f


def _bache(f, origen_id=1, lon=-79.8, lat=-3.2, **kw):
    datos = dict(fuente_id=f.id, origen_tipo="foto", origen_id=origen_id, hash_contenido="x" * 64,
                 geom=WKTElement(f"POINT({lon} {lat})", srid=4326), gps_origen="exif",
                 detectado_en=datetime(2026, 1, 1, tzinfo=timezone.utc), confianza=0.7)
    datos.update(kw)
    return Bache(**datos)


def test_health_conecta_con_bd_y_postgis(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    j = r.json()
    assert j["api"] and j["db"]
    assert j["postgis"]
    assert j["origen"]["configurado"] is False


def test_resumen_vacio(client):
    r = client.get("/api/resumen")
    assert r.status_code == 200
    assert r.json()["baches_total"] >= 0


def test_no_se_duplica_el_mismo_registro_de_origen(db):
    f = _fuente(db)
    db.add(_bache(f, origen_id=7))
    db.flush()
    db.add(_bache(f, origen_id=7))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_confianza_fuera_de_rango_se_rechaza(db):
    f = _fuente(db)
    db.add(_bache(f, confianza=1.5))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_consulta_espacial_por_distancia(db):
    f = _fuente(db)
    db.add_all([_bache(f, origen_id=1, lon=-79.8000, lat=-3.2000),
                _bache(f, origen_id=2, lon=-79.8010, lat=-3.2000),   # ~111 m al oeste
                _bache(f, origen_id=3, lon=-79.9000, lat=-3.2000)])  # ~11 km
    db.flush()
    centro = func.ST_GeogFromText("POINT(-79.8 -3.2)")
    cerca = db.scalars(select(Bache.origen_id).where(Bache.fuente_id == f.id,
                       func.ST_DWithin(Bache.geom, centro, 200))).all()
    assert sorted(cerca) == [1, 2]
    db.rollback()


def test_aviso_claro_si_postgis_no_esta_instalado(monkeypatch):
    """Si la extensión no existe en el servidor, se debe dar la instrucción de instalación (no un traceback)."""
    import sqlalchemy
    from app import schema_init

    original = sqlalchemy.text
    monkeypatch.setattr(schema_init, "text",
                        lambda q: original(q.replace("EXTENSION IF NOT EXISTS postgis", "EXTENSION IF NOT EXISTS postgis_inexistente")))
    with pytest.raises(schema_init.PostgisNoDisponible, match="Stack Builder"):
        schema_init.activar_postgis()
