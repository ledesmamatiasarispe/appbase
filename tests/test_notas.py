"""El módulo de ejemplo: así se testea un módulo (por la API de la app, con la base de prueba)."""
from tests.conftest import entrar_como, error


def test_datos_de_ejemplo_y_alta(api):
    assert {n["titulo"] for n in api.get("/api/notas").json()} == {"Bienvenida", "Probar la Ayuda"}
    assert "Falta el título" in error(api.post("/api/notas", json={"titulo": " "}))
    assert "prioridad" in error(api.post("/api/notas", json={"titulo": "X", "prioridad": "urgente"}))
    assert "fecha" in error(api.post("/api/notas", json={"titulo": "X", "vence": "31/02"}))
    n = api.post("/api/notas", json={"titulo": "Comprar repuestos", "prioridad": "alta", "vence": "2026-12-01"}).json()
    assert (n["prioridad"], n["vence"], n["creado_por"]) == ("alta", "2026-12-01", "Administrador")
    assert api.get("/api/notas").json()[0]["id"] == n["id"]   # las de prioridad alta primero


def test_archivar_es_de_administrador_y_no_borra(api):
    n = api.post("/api/notas", json={"titulo": "Temporal"}).json()
    api.post("/api/usuarios", json={"usuario": "op", "nombre": "Operario", "password": "123456"})
    h = entrar_como(api, "op", "123456", nueva="abcdef")
    assert api.post(f"/api/notas/{n['id']}/archivar", headers=h).status_code == 403
    assert api.post(f"/api/notas/{n['id']}/archivar").json()["activa"] == 0
    assert "archivada" in error(api.put(f"/api/notas/{n['id']}", json={"titulo": "Otro"}))
    assert any(x["id"] == n["id"] for x in api.get("/api/notas").json())   # sigue estando
    assert error(api.put("/api/notas/999", json={"titulo": "X"}), 404)
