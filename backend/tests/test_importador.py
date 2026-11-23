"""Pruebas del importador contra un origen SINTÉTICO (BD aparte `<nombre>_origen_test`, con la misma estructura
mínima que el proyecto original). No tocan ninguna base real."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app import importador
from app.config import settings
from app.db import SessionLocal, engine_origen
from app.models import Bache, Importacion, ImportacionError
from app.severidad import calcular
from tests.conftest import URL

DDL = """
DROP TABLE IF EXISTS video_hallazgos, videos, detecciones, capturas, tramos CASCADE;
CREATE TABLE tramos (id serial PRIMARY KEY, nombre text, ciudad text);
CREATE TABLE capturas (id serial PRIMARY KEY, tramo_id int, fecha_captura timestamptz, lat float8, lon float8,
  origen_gps text, ruta_imagen text, ancho int, alto int, modelo_version text, perfil text, parametros text);
CREATE TABLE detecciones (id serial PRIMARY KEY, captura_id int, clase text, confianza float8,
  x1 float8, y1 float8, x2 float8, y2 float8, area_frac float8);
CREATE TABLE videos (id serial PRIMARY KEY, tramo_id int, fecha_inicio timestamptz, ruta_gps text,
  modelo_version text, perfil text, parametros text);
CREATE TABLE video_hallazgos (id serial PRIMARY KEY, video_id int, clase text, t_ini float8, t_fin float8,
  n_apariciones int, conf_max float8, area_max float8, ruta_imagen text, lat float8, lon float8, descartado boolean);
"""

F = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)


# ───────────────────────── utilidades puras ─────────────────────────

def test_coordenadas_validas():
    assert importador.coordenadas_validas(-3.2, -79.8) is None
    assert "Sin coordenadas" in importador.coordenadas_validas(None, -79.8)
    assert "fuera de rango" in importador.coordenadas_validas(95, 10)
    assert "(0, 0)" in importador.coordenadas_validas(0, 0)
    assert "no numéricas" in importador.coordenadas_validas(float("nan"), 1)


def test_rumbo_hacia_el_norte_y_hacia_el_este():
    norte = [[-3.2000 + i * 0.0001, -79.8] for i in range(20)]           # sube de latitud
    assert importador.rumbo_desde_ruta(norte, -3.1990, -79.8) == pytest.approx(0, abs=1)
    este = [[-3.2, -79.8 + i * 0.0001] for i in range(20)]
    assert importador.rumbo_desde_ruta(este, -3.2, -79.799) == pytest.approx(90, abs=1)


def test_rumbo_no_se_inventa_si_no_hay_datos_fiables():
    assert importador.rumbo_desde_ruta(None, -3.2, -79.8) is None
    assert importador.rumbo_desde_ruta([[-3.2, -79.8]], -3.2, -79.8) is None
    detenido = [[-3.2, -79.8], [-3.20000001, -79.8], [-3.2, -79.80000001]]   # vehículo parado: ruido de GPS
    assert importador.rumbo_desde_ruta(detenido, -3.2, -79.8) is None
    lejos = [[-3.2 + i * 0.0001, -79.8] for i in range(20)]
    assert importador.rumbo_desde_ruta(lejos, -3.5, -79.8) is None         # el bache no está en la ruta
    assert importador.rumbo_desde_ruta([["x", 1], [2, 3]], 1, 1) is None


def test_ruta_segura_no_sale_de_su_carpeta(tmp_path):
    (tmp_path / "ok").mkdir()
    (tmp_path / "ok" / "a.jpg").write_bytes(b"x")
    assert importador.ruta_segura(tmp_path, "ok/a.jpg") == (tmp_path / "ok" / "a.jpg").resolve()
    assert importador.ruta_segura(tmp_path, "../fuera.jpg") is None
    assert importador.ruta_segura(tmp_path, "ok/../../fuera.jpg") is None
    assert importador.ruta_segura(tmp_path, "/etc/passwd") is None
    assert importador.ruta_segura(None, "ok/a.jpg") is None
    assert importador.ruta_segura(tmp_path, None) is None


def test_severidad_crece_con_tamano_confianza_y_persistencia():
    chico, _ = calcular(0.5, 0.002)
    grande, nivel_g = calcular(0.9, 0.10)
    assert grande > chico
    assert nivel_g == "alta"
    assert calcular(0.5, 0.01, n_apariciones=8)[0] > calcular(0.5, 0.01, n_apariciones=2)[0]
    assert calcular(1.0, None)[1] in ("baja", "media", "alta")      # sin área no falla
    assert 0 <= calcular(0, 0)[0] <= calcular(1, 1, 99)[0] <= 100


# ───────────────────────── origen sintético ─────────────────────────

@pytest.fixture(scope="module")
def origen_url():
    u = make_url(URL)
    nombre = f"{u.database.removesuffix('_test')}_origen_test"
    admin = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as con:
        if not con.scalar(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": nombre}):
            con.execute(text(f'CREATE DATABASE "{nombre}"'))
    admin.dispose()
    return u.set(database=nombre).render_as_string(hide_password=False)


@pytest.fixture()
def origen(origen_url, tmp_path, monkeypatch):
    """Crea el origen con casos conocidos y apunta la aplicación a él."""
    store = tmp_path / "origen_storage"
    (store / "capturas").mkdir(parents=True)
    (store / "videos/1").mkdir(parents=True)
    Image.new("RGB", (800, 600), (90, 90, 90)).save(store / "capturas/c1.jpg")
    Image.new("RGB", (360, 270), (60, 60, 60)).save(store / "videos/1/h_000.jpg")

    w = create_engine(origen_url)
    ruta = json.dumps([[-3.2000 + i * 0.0001, -79.8] for i in range(40)])     # el vehículo va hacia el norte
    with w.begin() as con:
        con.execute(text(DDL))
        con.execute(text("INSERT INTO tramos(nombre,ciudad) VALUES ('Av. Test','Pasaje')"))
        caps = [  # (lat, lon, origen_gps, imagen)
            (-3.2000, -79.8000, "exif", "capturas/c1.jpg"),            # 1: buena
            (None, None, None, "capturas/c1.jpg"),                       # 2: sin GPS
            (-3.2100, -79.8100, "manual", "capturas/no_existe.jpg"),    # 3: imagen inexistente
            (-3.2200, -79.8200, "exif", "../../etc/passwd"),             # 4: ruta maliciosa
            (0.0, 0.0, "exif", "capturas/c1.jpg"),                       # 5: GPS sin fijar
        ]
        for lat, lon, og, img in caps:
            con.execute(text("INSERT INTO capturas(tramo_id,fecha_captura,lat,lon,origen_gps,ruta_imagen,ancho,alto,"
                             "modelo_version,perfil,parametros) VALUES (1,:f,:la,:lo,:og,:im,800,600,'yolo26s','sensible',:pm)"),
                        dict(f=F, la=lat, lo=lon, og=og, im=img, pm='{"conf": 0.1}'))
        dets = [(1, "pothole", .8), (2, "pothole", .7), (1, "crack", .9), (3, "pothole", .6), (4, "pothole", .55),
                (5, "pothole", .5)]
        for cap, clase, conf in dets:
            con.execute(text("INSERT INTO detecciones(captura_id,clase,confianza,x1,y1,x2,y2,area_frac) "
                             "VALUES (:c,:cl,:co,300,250,500,400,0.0625)"), dict(c=cap, cl=clase, co=conf))
        con.execute(text("INSERT INTO videos(tramo_id,fecha_inicio,ruta_gps,modelo_version,perfil,parametros) "
                         "VALUES (1,:f,:r,'yolo26s','sensible','{}')"), dict(f=F, r=ruta))
        hall = [("pothole", 0.7, 20, False, "videos/1/h_000.jpg"),     # 1: buena, con rumbo
                ("pothole", 0.6, 30, True, "videos/1/h_000.jpg"),      # 2: descartado a mano
                ("crack", 0.9, 5, False, "videos/1/h_000.jpg"),        # 3: otra clase
                ("pothole", 0.5, 5, False, "videos/1/h_000.jpg")]      # 4: sin GPS
        for i, (cl, conf, lat_i, desc, img) in enumerate(hall, 1):
            lat = None if i == 4 else -3.2000 + lat_i * 0.0001
            lon = None if i == 4 else -79.8
            con.execute(text("INSERT INTO video_hallazgos(video_id,clase,t_ini,t_fin,n_apariciones,conf_max,area_max,"
                             "ruta_imagen,lat,lon,descartado) VALUES (1,:cl,4,6,5,:co,0.03,:im,:la,:lo,:d)"),
                        dict(cl=cl, co=conf, im=img, la=lat, lo=lon, d=desc))

    monkeypatch.setattr(settings, "origen_database_url", origen_url)
    monkeypatch.setattr(settings, "origen_storage_dir", str(store))
    monkeypatch.setattr(settings, "storage_dir", tmp_path / "propio")
    (tmp_path / "propio").mkdir()
    with SessionLocal() as db:
        db.execute(text("TRUNCATE importacion_errores, baches, importaciones, fuentes RESTART IDENTITY CASCADE"))
        db.commit()
    yield w, store
    w.dispose()


def correr(base_origen="usar", importa_error=False):
    """Una importación completa. Devuelve el objeto Importacion ya terminado."""
    base = Path(settings.origen_storage_dir) if base_origen == "usar" else base_origen
    imp_id = importador.crear_importacion(SessionLocal, "origen-test", "test:5432/x", str(base or ""))
    eng = engine_origen()
    try:
        importador.ejecutar_importacion(SessionLocal, eng, imp_id, base, settings.storage_path())
    finally:
        eng.dispose()
    with SessionLocal() as db:
        return db.get(Importacion, imp_id)


def baches():
    with SessionLocal() as db:
        return {(b.origen_tipo, b.origen_id): b for b in db.scalars(select(Bache))}


def test_primera_importacion_clasifica_cada_registro(origen):
    imp = correr()
    assert imp.estado == "completada", imp.mensaje
    assert imp.encontrados == 8                      # 5 fotos pothole + 3 hallazgos pothole (el 'crack' no cuenta)
    assert (imp.nuevos, imp.omitidos, imp.descartados, imp.errores) == (4, 3, 1, 0)
    assert imp.encontrados == imp.nuevos + imp.actualizados + imp.sin_cambios + imp.descartados + imp.omitidos + imp.errores
    assert imp.sin_evidencia == 2                    # foto con imagen inexistente y foto con ruta maliciosa

    b = baches()
    assert set(b) == {("foto", 1), ("foto", 4), ("foto", 5), ("video", 1)}   # id de DETECCIÓN, no de captura
    assert all(x.estado == "activo" and x.severidad_nivel for x in b.values())
    assert b[("foto", 1)].gps_origen == "exif" and b[("foto", 4)].gps_origen == "manual"
    assert b[("video", 1)].gps_origen == "gpx"
    assert b[("video", 1)].rumbo_grados == pytest.approx(0, abs=1)            # el vehículo iba hacia el norte
    assert b[("foto", 1)].tramo_nombre == "Av. Test" and b[("foto", 1)].ciudad == "Pasaje"

    # Evidencia: copia propia, con huella, y la foto es un RECORTE (más chico que los 800x600 originales)
    for clave in (("foto", 1), ("video", 1)):
        x = b[clave]
        p = settings.storage_path() / x.ruta_evidencia
        assert p.is_file() and len(x.evidencia_sha256) == 64
    with Image.open(settings.storage_path() / b[("foto", 1)].ruta_evidencia) as im:
        assert im.width < 800 and im.height < 600
    assert b[("foto", 4)].ruta_evidencia is None and b[("foto", 5)].ruta_evidencia is None

    with SessionLocal() as db:
        motivos = {e.motivo for e in db.scalars(select(ImportacionError))}
    assert any("Sin coordenadas" in m for m in motivos) and any("(0, 0)" in m for m in motivos)


def test_reimportar_no_duplica(origen):
    correr()
    imp = correr()
    assert imp.estado == "completada"
    assert (imp.nuevos, imp.actualizados, imp.sin_cambios) == (0, 0, 4)
    assert len(baches()) == 4


def test_cambio_en_el_origen_actualiza(origen):
    w, _ = origen
    correr()
    antes = baches()[("foto", 1)]
    with w.begin() as con:
        con.execute(text("UPDATE detecciones SET confianza = 0.95 WHERE id = 1"))
    imp = correr()
    assert (imp.nuevos, imp.actualizados, imp.sin_cambios) == (0, 1, 3)
    ahora = baches()[("foto", 1)]
    assert ahora.confianza == pytest.approx(0.95) and ahora.hash_contenido != antes.hash_contenido
    assert ahora.id == antes.id                                                # mismo registro, no uno nuevo


def test_descartar_y_reactivar_en_el_origen(origen):
    w, _ = origen
    correr()
    with w.begin() as con:
        con.execute(text("UPDATE video_hallazgos SET descartado = true WHERE id = 1"))
    imp = correr()
    assert imp.descartados == 2 and baches()[("video", 1)].estado == "descartado_origen"
    with w.begin() as con:
        con.execute(text("UPDATE video_hallazgos SET descartado = false WHERE id = 1"))
    imp = correr()
    assert imp.actualizados == 1 and baches()[("video", 1)].estado == "activo"


def test_lo_borrado_en_el_origen_se_marca_retirado_sin_perder_el_registro(origen):
    w, _ = origen
    correr()
    with w.begin() as con:
        con.execute(text("DELETE FROM detecciones WHERE id = 4"))                 # la detección 4 ya no existe en el origen
    imp = correr()
    assert imp.retirados == 1
    b = baches()
    assert b[("foto", 4)].estado == "retirado_origen"                             # se conserva, marcado
    assert imp.encontrados == 7


def test_evidencia_se_completa_si_el_storage_se_configura_despues(origen):
    imp1 = correr(base_origen=None)
    assert imp1.nuevos == 4 and imp1.sin_evidencia == 4
    assert all(b.ruta_evidencia is None for b in baches().values())
    imp2 = correr()                                                               # ahora con la carpeta del origen
    assert imp2.actualizados == 2 and imp2.nuevos == 0                            # foto 1 y video 1 reciben su imagen
    b = baches()
    assert b[("foto", 1)].ruta_evidencia and b[("video", 1)].ruta_evidencia


def test_un_registro_que_falla_no_detiene_a_los_demas(origen):
    w, _ = origen
    with w.begin() as con:
        con.execute(text("UPDATE detecciones SET confianza = 'NaN' WHERE id = 4"))   # viola la restricción 0..1
    imp = correr()
    assert imp.estado == "completada"
    assert imp.errores == 1 and imp.nuevos == 3
    assert imp.encontrados == imp.nuevos + imp.actualizados + imp.sin_cambios + imp.descartados + imp.omitidos + imp.errores
    assert ("foto", 4) not in baches() and ("foto", 1) in baches()
    with SessionLocal() as db:
        assert db.scalar(select(ImportacionError.motivo).where(ImportacionError.origen_id == 4,
                                                               ImportacionError.motivo.like("Error inesperado%")))


def test_origen_con_estructura_distinta_falla_con_mensaje_claro(origen):
    w, _ = origen
    with w.begin() as con:
        con.execute(text("ALTER TABLE video_hallazgos DROP COLUMN n_apariciones"))
    imp = correr()
    assert imp.estado == "fallida"
    assert "video_hallazgos.n_apariciones" in imp.mensaje
    assert baches() == {}


def test_la_conexion_al_origen_es_de_solo_lectura(origen):
    eng = engine_origen()
    try:
        with pytest.raises(DBAPIError, match="read-only"):
            with eng.begin() as con:
                con.execute(text("INSERT INTO tramos(nombre,ciudad) VALUES ('x','y')"))
        with eng.begin() as con:
            assert con.scalar(text("SELECT count(*) FROM tramos")) == 1           # el origen quedó intacto
    finally:
        eng.dispose()


def test_no_se_permiten_dos_importaciones_a_la_vez(origen):
    importador.crear_importacion(SessionLocal, "origen-test", "t", "")
    with pytest.raises(importador.ImportacionEnCurso):
        importador.crear_importacion(SessionLocal, "origen-test", "t", "")


def test_importacion_huerfana_se_marca_fallida_al_reiniciar(origen):
    i = importador.crear_importacion(SessionLocal, "origen-test", "t", "")
    assert importador.marcar_interrumpidas(SessionLocal) == 1
    with SessionLocal() as db:
        x = db.get(Importacion, i)
        assert x.estado == "fallida" and "reinició" in x.mensaje


# ───────────────────────── API ─────────────────────────

def test_api_importar_con_progreso_historial_y_errores(origen, client):
    r = client.post("/api/importaciones")
    assert r.status_code == 202
    iid = r.json()["id"]
    for _ in range(100):
        d = client.get(f"/api/importaciones/{iid}").json()
        if d["estado"] != "en_curso":
            break
        time.sleep(0.1)
    assert d["estado"] == "completada", d
    assert (d["encontrados"], d["nuevos"], d["omitidos"], d["descartados"]) == (8, 4, 3, 1)
    assert d["procesados"] == d["encontrados"]

    assert client.get("/api/importaciones").json()[0]["id"] == iid
    e = client.get(f"/api/importaciones/{iid}/errores").json()
    assert e["total"] == 3 and sum(e["por_motivo"].values()) == 3

    res = client.get("/api/resumen").json()
    assert res["baches_activos"] == 4 and res["por_origen"] == {"foto": 3, "video": 1}
    assert sum(res["por_severidad"].values()) == 4 and res["con_evidencia"] == 2

    assert client.get("/api/importaciones/9999").status_code == 404
    h = client.get("/api/health").json()
    assert h["origen"]["alcanzable"] and h["origen"]["storage"]


def test_api_rechaza_si_el_origen_no_esta_configurado(client, monkeypatch):
    monkeypatch.setattr(settings, "origen_database_url", "")
    r = client.post("/api/importaciones")
    assert r.status_code == 400 and "ORIGEN_DATABASE_URL" in r.json()["detail"]
