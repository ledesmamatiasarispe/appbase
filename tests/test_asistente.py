"""El asistente (modulos/asistente) con las notas como fuente: respuesta directa, resumen sin IA, con IA (un Ollama
falso en un puerto local, así el test no necesita Ollama instalado) y la IA que se cae a mitad de camino."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.conftest import api, error  # noqa: F401


def eventos(r):
    assert r.status_code == 200, r.text
    return [json.loads(x) for x in r.text.splitlines() if x.strip()]


def texto(evs):
    return "".join(e["texto"] for e in evs if e["tipo"] == "texto")


def preguntar(api, pregunta):
    return eventos(api.post("/api/asistente/preguntar", json={"pregunta": pregunta}))


@pytest.fixture()
def sin_ia(api):
    """La IA apuntando a un puerto donde no hay nada."""
    assert api.put("/api/asistente/ajustes", json={"url": "http://127.0.0.1:9", "modelo": "x"}).status_code == 200
    return api


@pytest.fixture()
def ollama_falso(api):
    pedidos = []

    class Falso(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            cuerpo = json.dumps({"models": [{"name": "modelo-falso:1b"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_POST(self):
            pedido = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            pedidos.append(pedido)
            self.send_response(200)
            self.end_headers()
            if "rompete" in pedido["messages"][-1]["content"]:
                self.wfile.write(b'{"message": {"content": "Empiezo"}, "done": false}\n')
                self.wfile.write(b'{"error": "se quedo sin memoria"}\n')
                return
            for pedazo in ("Según la nota, ", "hay que **comprar** guantes."):
                self.wfile.write(json.dumps({"message": {"content": pedazo}, "done": False}).encode() + b"\n")
            self.wfile.write(b'{"message": {"content": ""}, "done": true}\n')

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Falso)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{servidor.server_address[1]}"
    r = api.put("/api/asistente/ajustes", json={"url": url, "modelo": "modelo-falso:1b"})
    assert r.status_code == 200 and r.json()["disponible"], r.text
    yield pedidos
    servidor.shutdown()


def test_respuesta_directa_sin_ia(sin_ia):
    evs = preguntar(sin_ia, "¿Cuántas notas hay?")
    assert evs[0]["modo"] == "directa" and evs[-1]["tipo"] == "fin"
    assert texto(evs).startswith("Hay ") and evs[0]["enlaces"][0]["ir"] == "notas"


def test_sin_ia_muestra_el_resumen_y_avisa(sin_ia):
    sin_ia.post("/api/notas", json={"titulo": "Guantes", "texto": "Comprar guantes de cuero para el taller"})
    evs = preguntar(sin_ia, "¿qué hay que hacer con los guantes?")
    assert evs[0]["modo"] == "resumen" and "No se encontró la IA" in evs[0]["aviso"]
    assert "Comprar guantes" in texto(evs)


def test_nada_que_ver(sin_ia):
    evs = preguntar(sin_ia, "¿qwerty zxcvb?")
    assert evs[0]["modo"] == "nada" and "No encontré" in texto(evs)


def test_con_ia_redacta_con_los_datos(api, ollama_falso):
    api.post("/api/notas", json={"titulo": "Guantes", "texto": "Comprar guantes de cuero para el taller"})
    evs = preguntar(api, "¿qué hay que hacer con los guantes?")
    assert evs[0]["modo"] == "ia" and evs[0]["titulo"] == "Notas"
    assert texto(evs) == "Según la nota, hay que **comprar** guantes."
    mensaje = ollama_falso[-1]["messages"][-1]["content"]
    assert "DATOS:" in mensaje and "Comprar guantes de cuero" in mensaje and mensaje.endswith("guantes?")
    assert ollama_falso[-1]["model"] == "modelo-falso:1b" and ollama_falso[-1]["stream"] is True


def test_si_la_ia_se_cae_a_mitad_muestra_el_resumen(api, ollama_falso):
    api.post("/api/notas", json={"titulo": "Rompete", "texto": "rompete por favor"})
    evs = preguntar(api, "rompete")
    assert any(e["tipo"] == "aviso" and "no respondió" in e["aviso"] for e in evs)
    assert texto(evs).startswith("Empiezo") and "rompete por favor" in texto(evs)


def test_ayuda_y_saludo(sin_ia):
    for q in ("ayuda", "Hola", "¿qué puedo preguntar?"):
        inicio, texto = preguntar(sin_ia, q)[0], texto_de(preguntar(sin_ia, q))
        assert inicio["modo"] == "directa" and inicio["titulo"] == "Ayuda" and "barra de preguntas" in texto
        assert {"texto": "¿Cuántas notas hay?", "accion": "preguntar", "datos": {"pregunta": "¿Cuántas notas hay?"}} in inicio["enlaces"]


AYUDA = [{"pantalla": "notas", "titulo": "Nueva nota", "texto": "Para cargar una nota: botón Nueva nota, título y texto."},
         {"pantalla": "usuarios", "titulo": "Usuarios", "texto": "Para dar de alta a alguien: Nuevo usuario."}]


def test_preguntas_de_uso_con_la_ayuda_de_las_pantallas(sin_ia):
    r = sin_ia.post("/api/asistente/preguntar", json={"pregunta": "¿Cómo cargo una nota?", "ayuda": AYUDA})
    evs = eventos(r)
    assert evs[0]["titulo"] == "Cómo se usa la app" and "botón Nueva nota" in texto(evs)
    assert "Nuevo usuario" not in texto(evs)                       # solo los pasos que vienen al caso
    assert {"texto": "Ir a notas", "ir": "notas"} in evs[0]["enlaces"]
    # sin la ayuda de la pantalla, o algo que no está en ella, no inventa
    sin = eventos(sin_ia.post("/api/asistente/preguntar", json={"pregunta": "¿Cómo cargo un vuelo a Marte?", "ayuda": AYUDA}))
    assert sin[0]["modo"] == "nada" and "ayuda" in texto(sin)


def test_si_no_figura_y_sin_resultado(api, ollama_falso):
    from modulos.asistente import Fuente, registrar, servicios
    registrar(Fuente("prueba", contexto=lambda q: {"titulo": "X", "datos": "nada", "resumen": "nada",
                                                    "si_no_figura": {"texto": "¿Lo sabés?", "enlace": {"texto": "Cargarlo", "accion": "cargar"}}}
                     if "zapallo" in q else None,
                     sin_resultado=lambda q: {"texto": "No hay nada cargado sobre eso.", "enlaces": [{"texto": "Cargar", "accion": "cargar"}]}))
    try:
        evs = preguntar(api, "¿de qué color es el zapallo?")
        assert evs[0]["si_no_figura"]["enlace"]["accion"] == "cargar"
        evs = preguntar(api, "¿qwerty asdfg?")
        assert evs[0]["modo"] == "nada" and texto(evs) == "No hay nada cargado sobre eso." and evs[0]["enlaces"][0]["accion"] == "cargar"
    finally:
        servicios.FUENTES[:] = [f for f in servicios.FUENTES if f.nombre != "prueba"]


def texto_de(evs):
    return texto(evs)


def test_reiniciar_la_ia(api, ollama_falso, monkeypatch, tmp_path):
    """Se cierra y se abre Ollama (simulado: el test no toca procesos reales) y se espera a que vuelva a responder."""
    from modulos.asistente import servicios
    hecho = []
    monkeypatch.setattr(servicios, "_carpeta_ollama", lambda: tmp_path)
    monkeypatch.setattr(servicios, "_cerrar_ollama", lambda c: hecho.append(("cerrar", c)))
    monkeypatch.setattr(servicios, "_abrir_ollama", lambda c: hecho.append(("abrir", c)))
    monkeypatch.setattr(servicios.time, "sleep", lambda s: None)
    # la IA de la prueba está en 127.0.0.1: se puede reiniciar desde acá
    r = api.post("/api/asistente/reiniciar")
    assert r.status_code == 200 and r.json()["disponible"], r.text
    assert hecho == [("cerrar", tmp_path), ("abrir", tmp_path)]

    monkeypatch.setattr(servicios, "_carpeta_ollama", lambda: None)
    assert "No se encontró Ollama" in error(api.post("/api/asistente/reiniciar"))
    api.put("/api/asistente/ajustes", json={"url": "http://192.168.0.50:11434", "modelo": "x"})
    assert "otra PC" in error(api.post("/api/asistente/reiniciar"))


def test_si_no_vuelve_a_responder_avisa(sin_ia, monkeypatch, tmp_path):
    from modulos.asistente import servicios
    monkeypatch.setattr(servicios, "_carpeta_ollama", lambda: tmp_path)
    monkeypatch.setattr(servicios, "_cerrar_ollama", lambda c: None)
    monkeypatch.setattr(servicios, "_abrir_ollama", lambda c: None)
    monkeypatch.setattr(servicios.time, "sleep", lambda s: None)
    monkeypatch.setattr(servicios, "estado", lambda forzar=False: {"disponible": False, "modelos": []})
    reloj = iter(range(0, 1000, 10))
    monkeypatch.setattr(servicios.time, "time", lambda: next(reloj))
    assert "no respondió" in error(sin_ia.post("/api/asistente/reiniciar"))


def test_validaciones_y_permisos(api):
    assert "pregunta" in error(api.post("/api/asistente/preguntar", json={"pregunta": "   "}))
    assert error(api.post("/api/asistente/preguntar", json={"pregunta": "x" * 301}))
    assert "http://" in error(api.put("/api/asistente/ajustes", json={"url": "127.0.0.1:11434"}))
    # volver a lo de fábrica: vacío borra el ajuste
    r = api.put("/api/asistente/ajustes", json={"url": "", "modelo": ""}).json()
    assert (r["url"], r["modelo"]) == ("http://127.0.0.1:11434", "qwen2.5:3b")
    # un usuario común pregunta y ve el estado, pero no cambia los ajustes
    api.post("/api/usuarios", json={"usuario": "ana", "nombre": "Ana", "password": "clave-ana", "es_admin": False})
    api.headers["Authorization"] = "Bearer " + api.post("/api/auth/login", json={"usuario": "ana", "password": "clave-ana"}).json()["token"]
    assert api.get("/api/asistente/estado").status_code == 200
    assert api.put("/api/asistente/ajustes", json={"url": "http://x"}).status_code == 403
    assert api.post("/api/asistente/reiniciar").status_code == 403
