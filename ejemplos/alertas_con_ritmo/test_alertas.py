"""Alertas: reglas puras (ritmo "aparece N días antes / urgente con M o menos", niveles, cuotas, documentación, sin
seguro) y GET /api/alertas contra la base (flotas, renovaciones, pagos, bajas, filtros, una sola alerta por vehículo
al vencer el seguro, ritmo configurable en Opciones)."""
from datetime import date, timedelta

import pytest

from app import alertas as al
from tests.ayudas import cliente, dias, error, flota, ok, poliza, vehiculo
from tests.test_api import api  # noqa: F401

HOY = "2026-01-01"


def pol(**cambios) -> dict:
    p = {"id": 1, "numero": "123", "compania": "Compañía X", "vehiculo_id": 5, "dominio": "AAA123", "flota_id": None,
         "flota": None, "cliente_id": 9, "cliente": "Ficticio, Ana", "anulada": 0, "renovada_por_id": None,
         "vigencia_hasta": "2027-01-01", "proxima_cuota": None, "cantidad_cuotas": 3, "vencimiento_cuota": None,
         "frecuencia_refacturacion": "ninguna"}
    return {**p, **cambios}


def en(n: int) -> str:
    return (date.fromisoformat(HOY) + timedelta(days=n)).isoformat()


@pytest.mark.parametrize("faltan", range(-31, 20))
def test_vigencia_todos_los_dias_desde_n(faltan):
    """Con N=15 y M=3 (los de fábrica): aparece a los 15 y se ve TODOS los días hasta el vencimiento (no en escalones);
    roja con 3 o menos; vencida desde el día "hasta" y 30 días más."""
    a = al.alerta_vigencia(pol(vigencia_hasta=en(faltan)), HOY, 15, 3)
    if faltan > 15 or faltan < -30:
        assert a is None
        return
    esperado = "vencida" if faltan <= 0 else "urgente" if faltan <= 3 else "proxima"
    assert (a["tipo"], a["nivel"], a["dias"], a["aviso"], a["urgente_desde"], a["entidad"], a["entidad_id"]) == \
        ("vigencia", esperado, faltan, 15, 3, "poliza", 1)
    assert "123" in a["texto"] and "AAA123" in a["texto"]
    if faltan <= 0:
        assert "sin seguro" in a["texto"]


def test_vigencia_que_no_avisa():
    assert al.alerta_vigencia(pol(vigencia_hasta="2026-02-01"), HOY, 30, 3) is None             # faltan 31
    assert al.alerta_vigencia(pol(vigencia_hasta="2026-02-01"), HOY, 45, 3) is not None         # con otro aviso, sí
    assert al.alerta_vigencia(pol(vigencia_hasta="2026-01-05", renovada_por_id=2), HOY, 30, 3) is None
    assert al.alerta_vigencia(pol(vigencia_hasta="2026-01-05", anulada=1), HOY, 30, 3) is None
    assert al.alerta_vigencia(pol(vigencia_hasta="2026-01-05"), HOY, 30, 3, sucedida=True) is None
    f = al.alerta_vigencia(pol(vigencia_hasta="2026-01-05", vehiculo_id=None, dominio=None, flota_id=3, flota="Reparto"),
                           HOY, 30, 3)
    assert "flota 'Reparto'" in f["texto"] and f["flota_id"] == 3
    assert al.alerta_vigencia(pol(vigencia_hasta="2026-01-05"), HOY, 30, 4)["nivel"] == "urgente"   # M configurable
    assert al.alerta_vigencia(pol(vigencia_hasta="2026-01-05"), HOY, 30, 0)["nivel"] == "proxima"


def test_cuota():
    base = {"proxima_cuota": 2, "cantidad_cuotas": 3}
    assert al.alerta_cuota(pol(**base, vencimiento_cuota="2026-01-09"), HOY, 7, 3) is None          # faltan 8
    a = al.alerta_cuota(pol(**base, vencimiento_cuota="2026-01-08"), HOY, 7, 3)
    assert (a["nivel"], a["dias"], a["numero_cuota"], a["poliza_id"]) == ("proxima", 7, 2, 1)
    assert a["texto"].startswith("Cuota (cuota 2 de 3)")
    assert al.alerta_cuota(pol(**base, vencimiento_cuota="2026-01-04"), HOY, 7, 3)["nivel"] == "urgente"   # faltan 3
    assert al.alerta_cuota(pol(**base, vencimiento_cuota="2026-01-05"), HOY, 7, 3)["nivel"] == "proxima"   # faltan 4
    assert al.alerta_cuota(pol(**base, vencimiento_cuota="2026-01-01"), HOY, 7, 3)["nivel"] == "urgente"   # vence hoy
    v = al.alerta_cuota(pol(**base, vencimiento_cuota="2025-11-01", frecuencia_refacturacion="mensual"), HOY, 7, 3)
    assert v["nivel"] == "vencida" and v["texto"].startswith("Refacturación") and "venció" in v["texto"]
    assert al.alerta_cuota(pol(vencimiento_cuota="2026-01-02"), HOY, 7, 3) is None                  # todo pago
    assert al.alerta_cuota(pol(**base, vencimiento_cuota="2026-01-02", anulada=1), HOY, 7, 3) is None


def test_documento_y_sin_seguro():
    d = {"id": 4, "tipo": "VTV", "numero": "V-001", "titular": "AAA123", "vencimiento": "2026-01-01", "activo": 1,
         "renovado_por_id": None, "vehiculo_id": 5, "cliente_id": None, "dominio": "AAA123", "cliente": None}
    hoy = al.alerta_documento(d, HOY, 30, 3)
    assert hoy["nivel"] == "urgente" and "VTV n.º V-001 de AAA123" in hoy["texto"]   # el día del vencimiento vale
    assert al.alerta_documento({**d, "vencimiento": "2025-12-31"}, HOY, 30, 3)["nivel"] == "vencida"
    assert al.alerta_documento({**d, "vencimiento": "2026-01-04"}, HOY, 30, 3)["nivel"] == "urgente"
    assert al.alerta_documento({**d, "vencimiento": "2026-01-05"}, HOY, 30, 3)["nivel"] == "proxima"
    assert al.alerta_documento({**d, "vencimiento": "2026-01-31"}, HOY, 30, 3)["nivel"] == "proxima"
    assert al.alerta_documento({**d, "vencimiento": "2026-02-01"}, HOY, 30, 3) is None
    assert al.alerta_documento({**d, "renovado_por_id": 7}, HOY, 30, 3) is None
    assert "VTV de AAA123" in al.alerta_documento({**d, "numero": ""}, HOY, 30, 3)["texto"]   # uno viejo sin número
    v = {"id": 5, "dominio": "AAA123", "cliente_id": 9, "cliente": "Ficticio, Ana"}
    s = al.alerta_sin_seguro(v, HOY, "2025-12-20", "2026-01-10")
    assert (s["nivel"], s["dias"], s["entidad"]) == ("vencida", -12, "vehiculo") and "10/01/2026" in s["texto"]
    assert al.alerta_sin_seguro(v, HOY, None, None)["dias"] is None


def test_orden():
    lista = [al.alerta_vigencia(pol(id=1, vigencia_hasta="2026-01-10"), HOY, 15, 3),
             al.alerta_vigencia(pol(id=2, vigencia_hasta="2025-12-25"), HOY, 15, 3),
             al.alerta_vigencia(pol(id=3, vigencia_hasta="2026-01-03"), HOY, 15, 3)]
    assert [a["entidad_id"] for a in al.ordenar(lista)] == [2, 3, 1]


# ── contra la base ──

def tipos(api, tipo=""):
    return [(a["tipo"], a["entidad"], a["entidad_id"]) for a in ok(api.get(f"/api/alertas?tipo={tipo}"))]


def test_sin_seguro_no_cuenta_los_cubiertos_por_su_flota(api):
    cl = cliente(api)
    suelto = vehiculo(api, "AAA123", cl["id"])
    en_flota = vehiculo(api, "BBB222", cl["id"], desde=dias(-60))
    de_baja = vehiculo(api, "CCC333", cl["id"])
    ok(api.post(f"/api/vehiculos/{de_baja['id']}/baja"))
    fl = flota(api, cl["id"])
    ok(api.post(f"/api/flotas/{fl['id']}/vehiculos", json={"vehiculo_id": en_flota["id"], "desde": dias(-30)}))
    ok(poliza(api, "1", desde=dias(-10), hasta=dias(200), flota_id=fl["id"]))
    assert tipos(api, "sin_seguro") == [("sin_seguro", "vehiculo", suelto["id"])]
    a = ok(api.get("/api/alertas?tipo=sin_seguro"))[0]
    assert a["nivel"] == "vencida" and "nunca tuvo" in a["texto"] and a["cliente_id"] == cl["id"]
    ok(poliza(api, "2", desde=dias(-5), hasta=dias(300), vehiculo_id=suelto["id"]))
    assert tipos(api, "sin_seguro") == []


def test_vigencia_con_renovacion_o_con_otra_poliza(api):
    cl = cliente(api)
    v1, v2, v3 = (vehiculo(api, d, cl["id"]) for d in ("AAA123", "BBB222", "CCC333"))
    p1 = ok(poliza(api, "1", desde=dias(-300), hasta=dias(10), vehiculo_id=v1["id"]))
    p2 = ok(poliza(api, "2", desde=dias(-300), hasta=dias(10), vehiculo_id=v2["id"]))
    p3 = ok(poliza(api, "3", desde=dias(-300), hasta=dias(16), vehiculo_id=v3["id"]))   # fuera del aviso (15)
    assert tipos(api, "vigencia") == [("vigencia", "poliza", p1["id"]), ("vigencia", "poliza", p2["id"])]
    ok(api.post(f"/api/polizas/{p1['id']}/renovar", json={"numero": "11"}))
    ok(poliza(api, "22", desde=dias(10), hasta=dias(375), vehiculo_id=v2["id"]))   # otra póliza, no renovación
    assert tipos(api, "vigencia") == []
    assert p3["estado"] == "vigente"


def test_ritmo_configurable_en_opciones(api):
    """Las alertas, el estado por_vencer de la póliza y el de la documentación leen el MISMO ritmo."""
    cl = cliente(api)
    v = vehiculo(api, "AAA123", cl["id"])
    p = ok(poliza(api, "1", desde=dias(-300), hasta=dias(20), vehiculo_id=v["id"]))
    assert tipos(api, "vigencia") == [] and p["estado"] == "vigente"
    ok(api.patch("/api/opciones", json={"aviso_vigencia": 25, "urgente_vigencia": 20}))
    a = ok(api.get("/api/alertas?tipo=vigencia"))
    assert [(x["poliza_id"], x["nivel"], x["aviso"], x["urgente_desde"]) for x in a] == [(p["id"], "urgente", 25, 20)]
    assert ok(api.get(f"/api/polizas/{p['id']}"))["estado"] == "por_vencer"
    ok(api.patch("/api/opciones", json={"urgente_vigencia": 19}))
    assert ok(api.get("/api/alertas?tipo=vigencia"))[0]["nivel"] == "proxima"
    lic = next(t["id"] for t in ok(api.get("/api/documento-tipos")) if t["nombre"] == "Licencia de conducir")
    d = ok(api.post("/api/documentos", json={"tipo_id": lic, "cliente_id": cl["id"], "numero": "L-1", "vencimiento": dias(40)}))
    assert d["estado"] == "vigente" and tipos(api, "documentacion") == []
    ok(api.patch("/api/opciones", json={"aviso_documentacion": 40}))
    assert ok(api.get(f"/api/documentos/{d['id']}"))["estado"] == "por_vencer"
    assert [x["nivel"] for x in ok(api.get("/api/alertas?tipo=documentacion"))] == ["proxima"]


def test_una_sola_alerta_al_vencer_el_seguro(api):
    """Póliza vencida sin renovar: se ve la de vigencia (con la acción de renovar) y NO además "sin seguro" del mismo
    vehículo, mientras dure (30 días). Después, o sin póliza reciente, queda solo "sin seguro"."""
    cl = cliente(api)
    reciente, vieja, nunca = (vehiculo(api, d, cl["id"], desde=dias(-400)) for d in ("AAA123", "BBB222", "CCC333"))
    p1 = ok(poliza(api, "1", desde=dias(-100), hasta=dias(-5), vehiculo_id=reciente["id"]))
    ok(poliza(api, "2", desde=dias(-200), hasta=dias(-31), vehiculo_id=vieja["id"]))
    todas = tipos(api)
    assert ("vigencia", "poliza", p1["id"]) in todas
    assert ("sin_seguro", "vehiculo", reciente["id"]) not in todas
    assert {x for x in todas if x[0] == "sin_seguro"} == {("sin_seguro", "vehiculo", vieja["id"]),
                                                         ("sin_seguro", "vehiculo", nunca["id"])}
    # flota: la póliza de la flota venció -> una alerta (la de la flota), no una por vehículo; el que ya había salido
    # de la flota antes de que venciera sí queda "sin seguro"
    sigue, salio = vehiculo(api, "DDD444", cl["id"], desde=dias(-400)), vehiculo(api, "EEE555", cl["id"], desde=dias(-400))
    fl = flota(api, cl["id"])
    for x in (sigue, salio):
        ok(api.post(f"/api/flotas/{fl['id']}/vehiculos", json={"vehiculo_id": x["id"], "desde": dias(-90)}))
    pf = ok(poliza(api, "3", desde=dias(-80), hasta=dias(-2), flota_id=fl["id"]))
    ok(api.post(f"/api/flotas/{fl['id']}/vehiculos/{salio['id']}/quitar", json={"fecha": dias(-20)}))
    todas = tipos(api)
    assert ("vigencia", "poliza", pf["id"]) in todas and ("sin_seguro", "vehiculo", sigue["id"]) not in todas
    assert ("sin_seguro", "vehiculo", salio["id"]) in todas
    # al renovar, desaparecen las dos
    ok(api.post(f"/api/polizas/{p1['id']}/renovar", json={"numero": "11", "vigencia_hasta": dias(360)}))
    todas = tipos(api)
    assert ("vigencia", "poliza", p1["id"]) not in todas and ("sin_seguro", "vehiculo", reciente["id"]) not in todas


def test_cuota_desde_la_alerta_y_documentacion(api):
    ok(api.patch("/api/opciones", json={"avisar_cuotas": True}))   # apagado de fábrica
    cl = cliente(api)
    v = vehiculo(api, "AAA123", cl["id"])
    p = ok(poliza(api, "1", desde=dias(-20), hasta=dias(340), vehiculo_id=v["id"], cantidad_cuotas=3,
                  frecuencia_refacturacion="mensual", primer_vencimiento=dias(3)))
    a = ok(api.get("/api/alertas?tipo=cuota"))
    assert [(x["poliza_id"], x["numero_cuota"], x["nivel"]) for x in a] == [(p["id"], 1, "urgente")]
    ok(api.post(f"/api/polizas/{p['id']}/pagos", json={"fecha_pago": dias(0)}))   # la próxima, en un mes
    assert tipos(api, "cuota") == []
    vtv = next(t["id"] for t in ok(api.get("/api/documento-tipos")) if t["nombre"] == "VTV")
    d = ok(api.post("/api/documentos", json={"tipo_id": vtv, "vehiculo_id": v["id"], "numero": "V-1", "vencimiento": dias(-2)}))
    assert [(x["documento_id"], x["nivel"]) for x in ok(api.get("/api/alertas?tipo=documentacion"))] == [(d["id"], "vencida")]
    ok(api.post(f"/api/documentos/{d['id']}/renovar", json={"numero": "V-2", "vencimiento": dias(365)}))
    assert tipos(api, "documentacion") == []
    # con el vehículo de baja, su documentación deja de avisar
    ok(api.patch("/api/opciones", json={"aviso_documentacion": 365}))
    assert len(tipos(api, "documentacion")) == 1
    ok(api.post(f"/api/vehiculos/{v['id']}/baja"))
    assert tipos(api, "documentacion") == []


def test_filtros(api):
    cl = cliente(api)
    vehiculo(api, "AAA123", cl["id"])
    assert [a["nivel"] for a in ok(api.get("/api/alertas?nivel=vencida"))] == ["vencida"]
    assert ok(api.get("/api/alertas?nivel=proxima")) == []
    assert "elegir una de" in error(api.get("/api/alertas?tipo=otra"))
    assert "elegir una de" in error(api.get("/api/alertas?nivel=roja"))
    assert api.get("/api/alertas", headers={"Authorization": ""}).status_code == 401


def test_cuotas_apagadas_de_fabrica_y_se_prenden_desde_opciones(api):
    """Sin la opción: ni alerta ni cronograma de cuotas (la vigencia sí). Prendida, aparecen las dos."""
    v = vehiculo(api, "AAA123", cliente(api)["id"])
    p = ok(poliza(api, "1", desde=dias(-20), hasta=dias(10), vehiculo_id=v["id"], cantidad_cuotas=3,
                  primer_vencimiento=dias(2)))
    assert ok(api.get("/api/opciones"))["avisar_cuotas"] is False
    d = date.fromisoformat(dias(2))

    def ver():
        alertas = {a["tipo"] for a in ok(api.get("/api/alertas")) if a["poliza_id"] == p["id"]}
        eventos = {e["tipo"] for e in ok(api.get(f"/api/cronograma?anio={d.year}&mes={d.month}"))["eventos"]
                   if e["poliza_id"] == p["id"] and e["fecha"] == dias(2)}
        return alertas, eventos

    assert ver() == ({"vigencia"}, set())
    ok(api.patch("/api/opciones", json={"avisar_cuotas": True}))
    assert ver() == ({"vigencia", "cuota"}, {"cuota"})
    assert "no es sí ni no" in error(api.patch("/api/opciones", json={"avisar_cuotas": "quizás"}))
    ok(api.patch("/api/opciones", json={"avisar_cuotas": "no"}))
    assert ver() == ({"vigencia"}, set())
