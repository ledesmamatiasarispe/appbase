"""Auditoría: columnas creado/modificado en cada fila y el historial append-only, en la misma transacción."""
import sqlite3

import pytest

from app import db
from tests.ayudas import cliente, error, flota, ok, usuario_comun, vehiculo
from tests.test_api import api  # noqa: F401


def test_alta_y_edicion_quedan_en_el_historial_y_en_las_columnas(api):
    cl = cliente(api, "Pérez Inventado, Luis", telefono="111")
    assert cl["creado_por"] == "Administrador" and cl["creado_en"] and cl["modificado_en"] == cl["creado_en"]
    h = usuario_comun(api)
    ok(api.put(f"/api/clientes/{cl['id']}", json={"apellido_nombre": "Pérez Inventado, Luis", "telefono": "222"}, headers=h))
    ok(api.put(f"/api/clientes/{cl['id']}", json={"apellido_nombre": "Pérez Inventado, Luis", "telefono": "222"}, headers=h))
    hist = ok(api.get(f"/api/historial/cliente/{cl['id']}"))
    # la segunda edición no cambió nada: no deja renglón
    assert [x["accion"] for x in hist] == ["edicion", "alta"]
    assert hist[0]["antes"] == {"telefono": "111"} and hist[0]["despues"] == {"telefono": "222"}
    assert hist[0]["usuario"] == "Usuario 50" and hist[0]["legajo"] == 50
    assert hist[1]["despues"]["apellido_nombre"] == "Pérez Inventado, Luis"
    ficha = ok(api.get(f"/api/clientes/{cl['id']}"))
    assert ficha["modificado_por"] == "Usuario 50" and len(ficha["historial"]) == 2


def test_el_historial_no_se_modifica_ni_se_borra(api):
    cliente(api)
    conn = sqlite3.connect(db.DB_PATH)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="no se modifica"):
            conn.execute("UPDATE historial SET usuario='otro'")
        with pytest.raises(sqlite3.IntegrityError, match="no se borra"):
            conn.execute("DELETE FROM historial")
    finally:
        conn.close()


def test_si_el_caso_de_uso_falla_no_queda_ni_el_cambio_ni_su_rastro(api):
    """La venta cierra el titular y después intenta sacarlo de la flota: si eso falla, se deshace todo."""
    ana, beto = cliente(api, "Ana Ficticia"), cliente(api, "Beto Ficticio")
    v = vehiculo(api, "AAA111", ana["id"], desde="2026-01-01")
    f = flota(api, ana["id"])
    ok(api.post(f"/api/flotas/{f['id']}/vehiculos", json={"vehiculo_id": v["id"], "desde": "2026-06-01"}))
    antes = len(ok(api.get(f"/api/historial/vehiculo/{v['id']}")))
    assert "no puede salir antes" in error(api.post(f"/api/vehiculos/{v['id']}/venta",
                                                    json={"cliente_id": beto["id"], "fecha": "2026-03-01"}))
    ficha = ok(api.get(f"/api/vehiculos/{v['id']}"))
    assert ficha["cliente_id"] == ana["id"] and len(ficha["titulares"]) == 1
    assert len(ficha["historial"]) == antes


def test_historial_de_entidad_desconocida(api):
    assert "elegir una de" in error(api.get("/api/historial/usuarios/1"))
