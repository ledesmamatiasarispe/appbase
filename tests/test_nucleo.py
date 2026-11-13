"""El núcleo por la API de la app de ejemplo: sesión, usuarios, página, nombre y logo, puerto y transacciones."""
import socket
import threading
import time

from nucleo import ajustes, db, puerto as pto
from tests.conftest import entrar_como, error

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_sin_sesion_no_se_entra_y_la_provisoria_no_bloquea(api):
    assert api.get("/api/usuarios", headers={"Authorization": ""}).status_code == 401
    assert error(api.post("/api/auth/login", json={"usuario": "admin", "password": "mal"}), 401)
    api.post("/api/usuarios", json={"usuario": "ana", "nombre": "Ana", "password": "provisoria"})
    h = entrar_como(api, "ANA", "provisoria")   # el usuario no distingue mayúsculas
    assert api.get("/api/auth/yo", headers=h).json()["debe_cambiar"] is True
    assert api.get("/api/notas", headers=h).status_code == 200   # la provisoria no bloquea: la pantalla avisa
    api.post("/api/auth/password", json={"actual": "provisoria", "nueva": "propia-1"}, headers=h)
    assert api.get("/api/auth/yo", headers=h).json()["debe_cambiar"] is False


def test_reglas_de_usuarios(api):
    yo = api.get("/api/auth/yo").json()
    assert "único administrador" in error(api.put(f"/api/usuarios/{yo['id']}", json={"nombre": "Admin", "es_admin": False}))
    assert "a vos mismo" in error(api.post(f"/api/usuarios/{yo['id']}/baja"))
    assert "6 caracteres" in error(api.post("/api/usuarios", json={"usuario": "x", "nombre": "X", "password": "123"}))
    otro = api.post("/api/usuarios", json={"usuario": "beto", "nombre": "Beto", "password": "123456"}).json()
    assert "Ya existe" in error(api.post("/api/usuarios", json={"usuario": "BETO", "nombre": "Otro", "password": "123456"}))
    h = entrar_como(api, "beto", "123456", nueva="abcdef")
    assert api.get("/api/usuarios", headers=h).status_code == 403          # no es administrador
    assert api.post(f"/api/usuarios/{otro['id']}/baja").json()["activo"] == 0
    assert api.get("/api/auth/yo", headers=h).status_code == 401           # la baja cierra su sesión


def test_la_pagina_se_arma_con_los_modulos(api):
    pagina = api.get("/", headers={"Authorization": ""}).text
    assert f"<title>{ajustes.NOMBRE}</title>" in pagina and "{{" not in pagina
    assert 'data-vista="notas"' in pagina and f'/static/notas/notas.js?v={ajustes.VERSION}' in pagina
    assert pagina.index('data-vista="inicio"') < pagina.index('data-vista="notas"') < pagina.index('data-vista="usuarios"')
    assert pagina.index("/static/nucleo/nucleo.js") < pagina.index("/static/notas/notas.js")   # el módulo después del núcleo
    assert api.get("/static/notas/notas.js").status_code == 200 and api.get("/static/nucleo/ayuda.js").status_code == 200
    assert api.get("/api/version", headers={"Authorization": ""}).json() == {"version": ajustes.VERSION, "app": ajustes.APP}


def test_nombre_y_logo_de_la_app(api):
    sin_sesion = {"Authorization": ""}
    fabrica = {"nombre": ajustes.NOMBRE, "propio": False, "logo": None, "defecto": ajustes.NOMBRE}
    assert api.get("/api/marca").json() == fabrica
    assert api.put("/api/marca/nombre", json={"nombre": "  Taller   <Romero> "}).json()["nombre"] == "Taller <Romero>"
    pagina = api.get("/", headers=sin_sesion).text
    assert "<title>Taller &lt;Romero&gt;</title>" in pagina and "<Romero>" not in pagina
    assert "40 caracteres" in error(api.put("/api/marca/nombre", json={"nombre": "x" * 41}))
    assert "imagen" in error(api.post("/api/marca/logo", files={"archivo": ("logo.exe", b"MZ", "image/png")}))
    assert "no es un .png" in error(api.post("/api/marca/logo", files={"archivo": ("logo.png", b"MZ\x00", "image/png")}))
    logo = api.post("/api/marca/logo", files={"archivo": ("logo.png", PNG, "image/png")}).json()["logo"]
    pagina = api.get("/", headers=sin_sesion).text
    assert f"/api/marca/logo?v={logo}" in pagina and "icono.svg" not in pagina and 'type="image/png"' in pagina
    r = api.get("/api/marca/logo", headers=sin_sesion)
    assert r.content == PNG and "default-src 'none'" in r.headers["content-security-policy"]
    assert api.delete("/api/marca/logo").json()["logo"] is None and not (db.DB_PATH.parent / "marca" / logo).exists()
    assert api.put("/api/marca/nombre", json={"nombre": ""}).json() == fabrica


def _ocupar():
    s = socket.socket()
    s.bind(("0.0.0.0", 0))
    s.listen()
    return s, s.getsockname()[1]


def test_elegir_el_puerto_en_opciones(api, monkeypatch):
    monkeypatch.delenv(pto.VARIABLE, raising=False)
    monkeypatch.delenv(pto.VARIABLE_ACTUAL, raising=False)
    assert pto.VARIABLE == "BASE_PUERTO"
    assert api.get("/api/puerto").json()["elegido"] == ajustes.PUERTO
    assert "entre" in error(api.put("/api/puerto", json={"puerto": 80}))
    s, ocupado = _ocupar()
    with s:
        assert "otro programa" in error(api.put("/api/puerto", json={"puerto": ocupado}))
    libre = _ocupar()
    libre[0].close()
    assert api.put("/api/puerto", json={"puerto": libre[1]}).json()["elegido"] == libre[1] == pto.configurado()
    monkeypatch.setenv(pto.VARIABLE, "9999")
    assert pto.configurado() == 9999 and "variable" in error(api.put("/api/puerto", json={"puerto": 9100}))


def test_al_arrancar_esquiva_un_puerto_ocupado(monkeypatch):
    s, ocupado = _ocupar()
    with s:
        monkeypatch.delenv(pto.VARIABLE, raising=False)
        monkeypatch.setattr(pto, "configurado", lambda: ocupado)
        monkeypatch.setattr(pto, "quien_atiende", lambda p: None)   # lo ocupa otro programa
        puerto, ya_abierta = pto.al_arrancar()
        assert puerto > ocupado and not ya_abierta
        monkeypatch.setattr(pto, "quien_atiende", lambda p: ajustes.APP)   # lo ocupa esta misma app: se reusa
        assert pto.al_arrancar() == (ocupado, True)


def test_escrituras_de_a_una_y_transaccion_anidada(api, monkeypatch):
    """Dos casos de uso que validan leyendo: el segundo espera al primero y ve lo que escribió (no "database is locked")."""
    resultados = []

    def cargar(nombre):
        try:
            with db.transaccion() as c:
                ya = c.execute("SELECT count(*) FROM notas WHERE titulo='Única'").fetchone()[0]
                time.sleep(0.4)   # la ventana entre validar e insertar, donde estaría la carrera
                if ya:
                    raise ValueError("ya existe")
                c.execute("INSERT INTO notas (titulo) VALUES ('Única')")
            resultados.append("ok")
        except Exception as e:  # noqa: BLE001
            resultados.append(e)

    hilos = [threading.Thread(target=cargar, args=(n,)) for n in (1, 2)]
    hilos[0].start()
    time.sleep(0.1)
    hilos[1].start()
    for h in hilos:
        h.join(20)
    assert resultados[0] == "ok" and isinstance(resultados[1], ValueError), resultados
    # anidada: el bloque de adentro que falla deshace solo lo suyo
    with db.transaccion() as c:
        c.execute("INSERT INTO notas (titulo) VALUES ('Queda')")
        try:
            with db.transaccion() as c2:
                assert c2 is c
                c2.execute("INSERT INTO notas (titulo) VALUES ('Se deshace')")
                raise RuntimeError
        except RuntimeError:
            pass
    titulos = {n["titulo"] for n in api.get("/api/notas").json()}
    assert "Queda" in titulos and "Se deshace" not in titulos
