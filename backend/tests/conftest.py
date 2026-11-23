import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# La BD de pruebas es SEPARADA: las pruebas vacían sus tablas.
URL = os.environ.get("TEST_DATABASE_URL")
if not URL:
    pytest.skip("Define TEST_DATABASE_URL para ejecutar las pruebas (usa una BD aparte, p. ej. baches_mapa_test).",
                allow_module_level=True)
os.environ["DATABASE_URL"] = URL  # debe fijarse antes de importar la app

from app import schema_init  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def preparar_bd():
    assert make_url(URL).database.endswith("_test"), "La BD de pruebas debe terminar en _test"
    schema_init.crear_base_si_falta()
    schema_init.activar_postgis()
    Base.metadata.drop_all(engine)
    schema_init.crear_tablas()
    yield


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture()
def client():
    return TestClient(app)
