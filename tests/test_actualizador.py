"""Actualizaciones desde los releases de GitHub (GitHub simulado: nunca se sale a internet en los tests)."""
import hashlib
import io
import json
import ssl
import urllib.error
import zipfile
from datetime import date, timedelta

import pytest

from nucleo import actualizador as act
from tests.conftest import entrar_como, error

REPO = "romero/app"


def zip_con(archivos: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nombre, datos in archivos.items():
            z.writestr(nombre, datos)
    return buf.getvalue()


@pytest.fixture()
def github(monkeypatch):
    exe = act.v.exe()
    paquete = zip_con({f"App/{exe}": b"MZ nuevo", "App/_internal/x.txt": b"x"})
    respuestas = {
        act.API.format(repo=REPO): json.dumps({
            "tag_name": "v9.0.0", "body": "- Novedad 1", "html_url": "https://github.com/x",
            "assets": [{"name": "App-v9.0.0-win64.zip", "browser_download_url": "https://x/zip"},
                       {"name": "App-v9.0.0-win64.zip.sha256", "browser_download_url": "https://x/sha"}]}).encode(),
        "https://x/zip": paquete,
        "https://x/sha": (hashlib.sha256(paquete).hexdigest() + "  App-v9.0.0-win64.zip\n").encode(),
    }

    def pedir(url, timeout=10):
        if isinstance(respuestas.get(url), Exception):
            raise respuestas[url]
        return respuestas[url]

    monkeypatch.setattr(act, "_pedir", pedir)
    monkeypatch.setattr(act.v, "REPO", REPO)
    act._estado.clear()
    yield respuestas
    act._estado.clear()


def test_comparar_versiones():
    assert act.es_mas_nueva("v1.0.1", "1.0.0") and act.es_mas_nueva("v1.10.0", "1.9.9")
    assert not act.es_mas_nueva("v1.0.0", "1.0.0") and not act.es_mas_nueva("v1.0.0-beta", "1.0.0")


def test_hay_version_nueva_y_se_pregunta_solo_compilada(api, github, monkeypatch):
    a = api.get("/api/actualizacion").json()
    assert a["disponible"] and a["nueva"] == "v9.0.0" and a["instalable"] and not a["preguntar"]
    monkeypatch.setattr(act.v, "COMPILADA", True)
    assert api.get("/api/actualizacion").json()["preguntar"]
    hasta = api.post("/api/actualizacion/posponer").json()["pospuesta_hasta"]
    assert hasta == (date.today() + timedelta(days=7)).isoformat()
    assert not api.get("/api/actualizacion").json()["preguntar"]


def test_sin_internet_o_sin_certificado_no_rompe(api, github, monkeypatch):
    github[act.API.format(repo=REPO)] = OSError("sin red")
    assert "No se pudo consultar GitHub" in api.post("/api/actualizacion/buscar").json()["error"]
    github[act.API.format(repo=REPO)] = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
    assert api.post("/api/actualizacion/buscar").json()["error"] is None   # sin releases todavía: no es un error


def test_sin_certificado_explica_que_hacer(monkeypatch):
    def falla(*a, **k):
        raise urllib.error.URLError(ssl.SSLCertVerificationError("unable to get local issuer certificate"))
    monkeypatch.setattr(act.urllib.request, "urlopen", falla)
    with pytest.raises(act.ErrorDeNegocio, match="antivirus o un proxy"):
        act._pedir("https://api.github.com/x")


def test_preparar_controla_el_hash_y_las_rutas(github, tmp_path):
    info = act.buscar(forzar=True)
    assert (act.preparar(info, tmp_path / "act") / act.v.exe()).read_bytes() == b"MZ nuevo"
    github["https://x/sha"] = b"0" * 64
    with pytest.raises(act.ErrorDeNegocio, match="SHA-256"):
        act.preparar(info, tmp_path / "act")
    malo = tmp_path / "malo.zip"
    malo.write_bytes(zip_con({"../../fuera.txt": b"x", act.v.exe(): b"MZ"}))
    with pytest.raises(act.ErrorDeNegocio, match="rutas inválidas"):
        act._extraer(malo, tmp_path / "nueva")


def test_copia_de_la_base_y_bat_con_vuelta_atras(api, tmp_path):
    for n in range(1, 6):
        assert act.respaldar_base(f"v9.0.{n}").exists()
    copias = sorted(p.name for p in act.db.DB_PATH.parent.glob("*_antes_de_v*.db"))
    assert len(copias) == act.COPIAS_A_GUARDAR and copias[-1].endswith("v9.0.5.db")
    bat = act.script_windows(nueva=tmp_path / "nueva", instalacion=tmp_path / "app", trabajo=tmp_path / "data" / "act",
                             version_nueva="v9.0.0", pid=1234)
    assert bat.index('"anterior"' if False else "anterior") < bat.index("if errorlevel 8") and "/XD" in bat


def test_permisos(api, github):
    assert "versión compilada" in error(api.post("/api/actualizacion/instalar"))
    api.post("/api/usuarios", json={"usuario": "op", "nombre": "Operario", "password": "provisoria"})
    h = entrar_como(api, "op", "provisoria", nueva="propia-123")
    assert api.get("/api/actualizacion", headers=h).json()["preguntar"] is False
    assert api.post("/api/actualizacion/instalar", headers=h).status_code == 403
