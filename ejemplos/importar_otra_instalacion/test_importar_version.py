"""Traer los datos de otra instalación (versión vieja): revisar, validar, respaldar, reemplazar y migrar."""
import sqlite3

import pytest

from app import db, secretos
from app.auth import hash_password
from tests.ayudas import cliente, error, ok, usuario_comun
from tests.test_api import api  # noqa: F401

VIEJO = "CHECK ((vehiculo_id IS NULL) <> (flota_id IS NULL))"


@pytest.fixture()
def vieja(tmp_path):
    """Una instalación 0.1.1 en otra carpeta: base con el esquema de entonces, un adjunto y su clave."""
    carpeta = tmp_path / "GestionAutomotorAPB-viejo"
    datos = carpeta / "data"
    (datos / "adjuntos" / "polizas" / "1").mkdir(parents=True)
    (datos / "adjuntos" / "polizas" / "1" / "abc.pdf").write_bytes(b"%PDF-1.4 vieja")
    (datos / secretos.ARCHIVO_CLAVE).write_bytes(b"clave-de-la-vieja")
    conn = sqlite3.connect(datos / "automotor.db")
    conn.executescript(db.ESQUEMA.replace("CHECK (vehiculo_id IS NULL OR flota_id IS NULL)", VIEJO))
    salt, h = hash_password("vieja123")
    conn.execute("INSERT INTO usuarios (legajo, nombre, password_hash, salt, es_admin) VALUES (7, 'Admin Viejo', ?, ?, 1)", (h, salt))
    conn.executescript("""
        INSERT INTO companias (id, nombre) VALUES (1, 'Compañía Ficticia');
        INSERT INTO clientes (id, apellido_nombre) VALUES (1, 'Ficticio Viejo, Ana');
        INSERT INTO vehiculos (id, dominio) VALUES (1, 'AAA123');
        INSERT INTO polizas (id, compania_id, numero, cliente_id, vehiculo_id, vigencia_desde, vigencia_hasta)
             VALUES (1, 1, '1', 1, 1, '2026-01-01', '2027-01-01');""")
    conn.commit()
    conn.close()
    return carpeta


def test_revisar_muestra_lo_que_se_trae_sin_tocar_nada(api, vieja):
    cliente(api, "Ficticio Actual, Beto")
    r = ok(api.post("/api/importar-version/revisar", json={"ruta": str(vieja)}))
    assert r["importar"]["clientes"] == 1 and r["importar"]["pólizas"] == 1 and r["actual"]["clientes"] == 1
    assert r["adjuntos"] == 1 and r["clave"] is True
    assert r["ruta_base"].endswith("automotor.db")
    # también con la carpeta data o el archivo directo, y entre comillas (como lo copia el explorador)
    ok(api.post("/api/importar-version/revisar", json={"ruta": str(vieja / "data")}))
    ok(api.post("/api/importar-version/revisar", json={"ruta": f'"{vieja / "data" / "automotor.db"}"'}))
    assert [c["apellido_nombre"] for c in ok(api.get("/api/clientes"))] == ["Ficticio Actual, Beto"]


def test_validaciones(api, vieja, tmp_path):
    assert "Falta la carpeta" in error(api.post("/api/importar-version/revisar", json={"ruta": " "}))
    assert "No se encontró automotor.db" in error(api.post("/api/importar-version/revisar", json={"ruta": str(tmp_path / "nada")}))
    assert "ya está usando" in error(api.post("/api/importar-version/revisar", json={"ruta": str(db.DB_PATH)}))
    otra = tmp_path / "otra"
    otra.mkdir()
    (otra / "automotor.db").write_bytes(b"esto no es una base")
    assert "no es una base de datos" in error(api.post("/api/importar-version", json={"ruta": str(otra)}))
    sqlite3.connect(otra / "ajena.db").execute("CREATE TABLE cosas (x)").connection.commit()
    assert "le faltan las tablas" in error(api.post("/api/importar-version/revisar", json={"ruta": str(otra / "ajena.db")}))
    # solo un administrador
    h = usuario_comun(api)
    assert api.post("/api/importar-version/revisar", json={"ruta": str(vieja)}, headers=h).status_code == 403
    assert api.post("/api/importar-version", json={"ruta": str(vieja)}, headers=h).status_code == 403


def test_importar_reemplaza_respalda_y_migra(api, vieja):
    cliente(api, "Ficticio Actual, Beto")
    datos = db.DB_PATH.parent
    (datos / "adjuntos" / "fotos").mkdir(parents=True, exist_ok=True)
    (datos / "adjuntos" / "fotos" / "actual.jpg").write_bytes(b"\xff\xd8 actual")
    clave_actual = secretos.ruta_clave().read_bytes() if secretos.ruta_clave().is_file() else None

    r = ok(api.post("/api/importar-version", json={"ruta": str(vieja)}))
    assert r["importados"]["clientes"] == 1 and r["importados"]["usuarios"] == 1
    # lo de antes quedó respaldado entero
    from pathlib import Path
    respaldo = Path(r["respaldo"])
    copia = sqlite3.connect(respaldo / "automotor.db")
    assert copia.execute("SELECT apellido_nombre FROM clientes").fetchall() == [("Ficticio Actual, Beto",)]
    copia.close()
    assert (respaldo / "adjuntos" / "fotos" / "actual.jpg").read_bytes() == b"\xff\xd8 actual"
    if clave_actual:
        assert (respaldo / secretos.ARCHIVO_CLAVE).read_bytes() == clave_actual
    # los adjuntos y la clave ahora son los de la vieja; la vieja no se tocó
    assert (datos / "adjuntos" / "polizas" / "1" / "abc.pdf").read_bytes() == b"%PDF-1.4 vieja"
    assert not (datos / "adjuntos" / "fotos" / "actual.jpg").exists()
    assert secretos.ruta_clave().read_bytes() == b"clave-de-la-vieja"
    assert (vieja / "data" / "automotor.db").is_file()

    # la sesión de antes ya no vale: se entra con los usuarios de la base importada
    assert api.get("/api/clientes").status_code == 401
    tok = ok(api.post("/api/auth/login", json={"legajo": 7, "password": "vieja123"}, headers={"Authorization": ""}))["token"]
    api.headers["Authorization"] = f"Bearer {tok}"
    assert [c["apellido_nombre"] for c in ok(api.get("/api/clientes"))] == ["Ficticio Viejo, Ana"]
    # quedó en el esquema de esta versión: admite pólizas personales y personas aseguradas
    p = ok(api.post("/api/polizas", json={"compania_id": 1, "numero": "2", "cliente_id": 1, "vigencia_desde": "2026-01-01",
                                          "vigencia_hasta": "2027-01-01"}))
    ok(api.post(f"/api/polizas/{p['id']}/asegurados", json={"nombre": "Tercero Ficticio"}))
    with db.transaccion() as c:
        h = c.execute("SELECT usuario, despues FROM historial WHERE entidad='sistema' AND accion='importacion_version'").fetchone()
    assert h["usuario"] and "GestionAutomotorAPB-viejo" in h["despues"]


def test_un_respaldo_de_la_misma_carpeta_data_no_borra_los_adjuntos(api):
    """Elegir otro .db de esta misma carpeta data (un respaldo viejo): la base vuelve, los adjuntos se quedan."""
    datos = db.DB_PATH.parent
    (datos / "adjuntos" / "fotos").mkdir(parents=True, exist_ok=True)
    (datos / "adjuntos" / "fotos" / "actual.jpg").write_bytes(b"\xff\xd8")
    cliente(api, "Ficticio Antes, Ana")
    viejo = sqlite3.connect(datos / "automotor_antes_de_algo.db")
    sqlite3.connect(db.DB_PATH).backup(viejo)
    viejo.close()
    cliente(api, "Ficticio Despues, Beto")
    ok(api.post("/api/importar-version", json={"ruta": str(datos / "automotor_antes_de_algo.db")}))
    assert (datos / "adjuntos" / "fotos" / "actual.jpg").is_file()
    with db.transaccion() as c:
        assert [r[0] for r in c.execute("SELECT apellido_nombre FROM clientes ORDER BY id")] == ["Ficticio Antes, Ana"]
