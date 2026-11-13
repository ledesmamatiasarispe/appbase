"""Los tests usan la app de ejemplo (app/) con una base nueva en una carpeta temporal, nunca una real, y nunca salen a
internet: sin repositorio, la app no busca actualizaciones en GitHub."""
import os

os.environ["BASE_REPO"] = ""

import app.main  # noqa: E402,F401  (configura el núcleo ANTES de que cada test cambie db.DB_PATH)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def api(tmp_path, monkeypatch):
    """Cliente con el administrador de fábrica logueado y su contraseña ya cambiada."""
    from nucleo import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "prueba.db")
    from app.main import app
    with TestClient(app) as cliente:
        r = cliente.post("/api/auth/login", json={"usuario": "admin", "password": "admin"})
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        cliente.headers["Authorization"] = f"Bearer {token}"
        assert cliente.post("/api/auth/password", json={"actual": "admin", "nueva": "clave-admin"}).status_code == 200
        yield cliente


def error(r, status=400):
    assert r.status_code == status, r.text
    return r.json()["detail"]


def entrar_como(api, usuario, password, nueva=None) -> dict:
    """Headers de otro usuario (opcionalmente con su contraseña ya cambiada)."""
    tok = api.post("/api/auth/login", json={"usuario": usuario, "password": password}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    if nueva:
        api.post("/api/auth/password", json={"actual": password, "nueva": nueva}, headers=h)
    return h
