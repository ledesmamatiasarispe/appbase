"""Resumen semanal por mail: período programado, armado (texto + HTML escapado), envío con smtplib REEMPLAZADO
(ningún test manda un mail de verdad), registro append-only, no repetir el período, reintento, prueba y programador."""
import sqlite3
from datetime import datetime, timedelta

import pytest

from app import correo, db, secretos
from tests.ayudas import cliente, error, ok, usuario_comun, vehiculo
from tests.test_api import api  # noqa: F401


class FalsoSMTP:
    """Reemplaza smtplib.SMTP y SMTP_SSL: anota lo que se hizo y lo que se mandó."""
    instancias: list = []
    enviados: list = []
    falla: Exception | None = None

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.acciones = host, port, []
        FalsoSMTP.instancias.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def starttls(self, context=None):
        self.acciones.append("starttls")

    def login(self, usuario, password):
        self.acciones.append(("login", usuario, password))
        if FalsoSMTP.falla:
            raise FalsoSMTP.falla

    def send_message(self, msg):
        FalsoSMTP.enviados.append(msg)


class FalsoSSL(FalsoSMTP):
    pass


@pytest.fixture()
def smtp(monkeypatch):
    FalsoSMTP.instancias, FalsoSMTP.enviados, FalsoSMTP.falla = [], [], None
    monkeypatch.setattr(correo.smtplib, "SMTP", FalsoSMTP)
    monkeypatch.setattr(correo.smtplib, "SMTP_SSL", FalsoSSL)
    return FalsoSMTP


def configurar(api, **extra):
    return ok(api.patch("/api/opciones", json={"smtp_servidor": "smtp.ejemplo.com", "smtp_puerto": 587,
                                               "smtp_usuario": "cuenta@ejemplo.com", "smtp_password": "clave-inventada",
                                               "smtp_remitente": "avisos@ejemplo.com", "smtp_seguridad": "tls",
                                               "mail_destinatarios": ["productor@ejemplo.com", "socio@ejemplo.com"],
                                               **extra}))


# ── puro ──

@pytest.mark.parametrize("ahora,esperado", [
    (datetime(2026, 11, 4, 10, 0), datetime(2026, 11, 2, 8, 0)),    # miércoles: el del lunes pasado
    (datetime(2026, 11, 9, 7, 59), datetime(2026, 11, 2, 8, 0)),    # lunes antes de hora: todavía el anterior
    (datetime(2026, 11, 9, 8, 0), datetime(2026, 11, 9, 8, 0)),     # lunes a la hora: el nuevo
    (datetime(2026, 11, 8, 23, 0), datetime(2026, 11, 2, 8, 0)),    # domingo
])
def test_periodo(ahora, esperado):
    assert correo.periodo(ahora, "lunes", "08:00") == esperado


def test_periodo_otro_dia():
    assert correo.periodo(datetime(2026, 11, 4, 10, 0), "viernes", "17:30") == datetime(2026, 10, 30, 17, 30)


def test_armar_escapa_y_agrupa():
    a = [{"tipo": "vigencia", "nivel": "urgente", "texto": "Vence la póliza de <b>Ficticio</b> & Cía"},
         {"tipo": "sin_seguro", "nivel": "vencida", "texto": "AAA123 sin seguro"}]
    m = correo.armar(a, "2026-11-04")
    assert "2 vencimientos" in m["asunto"] and "04/11/2026" in m["asunto"]
    assert "&lt;b&gt;Ficticio&lt;/b&gt; &amp; Cía" in m["html"] and "<b>Ficticio" not in m["html"]
    assert m["texto"].index("VENCIDAS (1)") < m["texto"].index("URGENTES (1)")
    vacio = correo.armar([], "2026-11-04", prueba=True)
    assert vacio["asunto"].startswith("[PRUEBA]") and "No hay vencimientos" in vacio["texto"]


# ── programador ──

def envios_semanales():
    with db.transaccion() as c:
        return [dict(r) for r in c.execute("SELECT * FROM envios_mail WHERE tipo='semanal' ORDER BY id")]


def test_sin_configurar_no_intenta(api, smtp):
    assert correo.revisar(datetime(2026, 11, 4, 10, 0)) is None
    ok(api.patch("/api/opciones", json={"smtp_servidor": "smtp.ejemplo.com", "smtp_usuario": "cuenta@ejemplo.com"}))
    assert correo.revisar(datetime(2026, 11, 4, 10, 0)) is None   # sin destinatarios
    assert smtp.instancias == [] and envios_semanales() == []


def test_manda_al_arrancar_una_vez_por_periodo(api, smtp):
    cl = cliente(api)
    vehiculo(api, "AAA123", cl["id"])   # sin seguro: una alerta
    configurar(api)
    e = correo.revisar(datetime(2026, 11, 4, 10, 0))   # estaba apagada el lunes 08:00: sale ahora
    assert (e["resultado"], e["periodo"], e["usuario"], e["cantidad_alertas"]) == ("ok", "2026-11-02T08:00", "Sistema", 1)
    assert e["destinatarios"] == ["productor@ejemplo.com", "socio@ejemplo.com"] and "AAA123" in e["resumen"]
    s = smtp.instancias[0]
    assert (s.host, s.port) == ("smtp.ejemplo.com", 587)
    assert s.acciones == ["starttls", ("login", "cuenta@ejemplo.com", "clave-inventada")]
    msg = smtp.enviados[0]
    assert msg["To"] == "productor@ejemplo.com, socio@ejemplo.com" and msg["From"] == "avisos@ejemplo.com"
    assert msg.get_body(("html",)) is not None and "AAA123" in msg.get_body(("plain",)).get_content()
    # el mismo período no sale de nuevo
    assert correo.revisar(datetime(2026, 11, 4, 10, 1)) is None
    assert correo.revisar(datetime(2026, 11, 9, 7, 59)) is None
    # el lunes siguiente a la hora, sí
    assert correo.revisar(datetime(2026, 11, 9, 8, 0))["periodo"] == "2026-11-09T08:00"
    # cambiar el día no repite lo que ya salió después del nuevo momento programado
    ok(api.patch("/api/opciones", json={"resumen_dia": "domingo"}))
    assert correo.revisar(datetime(2026, 11, 9, 9, 0)) is None
    assert len(smtp.enviados) == 2 and len(envios_semanales()) == 2


def test_falla_queda_registrada_y_se_reintenta(api, smtp):
    configurar(api)
    smtp.falla = correo.smtplib.SMTPAuthenticationError(535, b"credenciales invalidas")
    e = correo.revisar(datetime(2026, 11, 9, 8, 0))
    assert e["resultado"] == "error" and "SMTPAuthenticationError" in e["error"]
    assert correo.revisar(datetime(2026, 11, 9, 8, 30)) is None   # no insiste enseguida
    smtp.falla = None
    assert correo.revisar(datetime(2026, 11, 9, 9, 1))["resultado"] == "ok"
    assert [x["resultado"] for x in envios_semanales()] == ["error", "ok"]


def test_ssl_usa_smtp_ssl(api, smtp):
    configurar(api, smtp_seguridad="ssl", smtp_puerto=465)
    correo.revisar(datetime(2026, 11, 9, 8, 0))
    assert isinstance(smtp.instancias[0], FalsoSSL) and smtp.instancias[0].acciones[0] != "starttls"


def test_registro_append_only(api, smtp):
    configurar(api)
    correo.revisar(datetime(2026, 11, 9, 8, 0))
    with db.transaccion() as c:
        for sql in ("UPDATE envios_mail SET resultado='error'", "DELETE FROM envios_mail"):
            with pytest.raises(sqlite3.DatabaseError):
                c.execute(sql)
        with pytest.raises(sqlite3.IntegrityError):   # dos exitosos del mismo período: el índice no deja
            c.execute("INSERT INTO envios_mail (cuando, tipo, periodo, usuario, destinatarios, asunto, resultado, "
                      "cantidad_alertas, resumen) VALUES ('x', 'semanal', '2026-11-09T08:00', 'S', '[]', 'a', 'ok', 0, '')")


def test_programador_apagado_con_auto_mail_0():
    assert correo.programador_activo() is False and correo.iniciar_programador() is False


# ── rutas ──

def test_prueba_envios_estado_solo_admin(api, smtp):
    h = usuario_comun(api)
    for ruta in ("/api/mail/envios", "/api/mail/estado", "/api/mail/vista-previa"):
        assert api.get(ruta, headers=h).status_code == 403
    assert api.post("/api/mail/prueba", json={}, headers=h).status_code == 403
    assert "servidor SMTP" in error(api.post("/api/mail/prueba", json={}))
    configurar(api)
    e = ok(api.post("/api/mail/prueba", json={"mail": "yo@ejemplo.com"}))
    assert (e["tipo"], e["destinatarios"], e["usuario"]) == ("prueba", ["yo@ejemplo.com"], "Administrador")
    assert smtp.enviados[0]["Subject"].startswith("[PRUEBA]")
    assert "no es una dirección" in error(api.post("/api/mail/prueba", json={"mail": "mal"}))
    smtp.falla = OSError("sin conexión")
    assert "No se pudo mandar" in error(api.post("/api/mail/prueba", json={}))
    lista = ok(api.get("/api/mail/envios"))
    assert [(x["tipo"], x["resultado"]) for x in lista] == [("prueba", "error"), ("prueba", "ok")]
    assert "clave-inventada" not in api.get("/api/mail/envios").text
    est = ok(api.get("/api/mail/estado"))
    assert est["configurado"] and est["programador_activo"] is False and est["ultimo_envio"] is None   # la prueba no cuenta
    assert "clave-inventada" not in str(est)
    vp = ok(api.get("/api/mail/vista-previa"))
    assert set(vp) == {"asunto", "texto", "html", "cantidad_alertas", "adelanto"}


def test_estado_proximo_envio(api, smtp):
    configurar(api)
    assert correo.estado(datetime(2026, 11, 4, 10, 0))["proximo"] == "2026-11-02T08:00"   # pendiente: sale ya
    correo.revisar(datetime(2026, 11, 4, 10, 0))
    assert correo.estado(datetime(2026, 11, 4, 10, 5))["proximo"] == "2026-11-09T08:00"


# ── mail sin alertas: una semana más ──

def licencia(api, cl, vence):
    lic = next(t["id"] for t in ok(api.get("/api/documento-tipos")) if t["nombre"] == "Licencia de conducir")
    return ok(api.post("/api/documentos", json={"tipo_id": lic, "cliente_id": cl["id"], "numero": "L-1", "vencimiento": vence}))


def test_armar_adelanto():
    a = [{"tipo": "documentacion", "nivel": "proxima", "texto": "Licencia de conducir n.º L-1 de Ficticio"}]
    m = correo.armar(a, "2026-11-04", adelanto=True)
    assert "semana siguiente" in m["asunto"] and correo.texto_adelanto() in m["texto"]
    assert "Licencia de conducir" in m["texto"] and "período habitual" in m["html"]
    assert "semana siguiente" not in correo.armar(a, "2026-11-04")["asunto"]


def test_sin_alertas_extiende_una_semana(api, smtp):
    """Documentación aparece 30 días antes: a 35 días no hay alerta, pero el resumen mira 7 días más y la manda
    avisando que es lo que viene después. La vista previa muestra exactamente lo mismo."""
    cl = cliente(api)
    d = licencia(api, cl, (datetime.now().date() + timedelta(days=35)).isoformat())
    assert ok(api.get("/api/alertas")) == []
    vp = ok(api.get("/api/mail/vista-previa"))
    assert (vp["adelanto"], vp["cantidad_alertas"]) == (True, 1) and "semana siguiente" in vp["asunto"]
    assert correo.texto_adelanto() in vp["texto"] and "L-1" in vp["texto"]
    configurar(api)
    e = correo.revisar(datetime.now())
    assert e["cantidad_alertas"] == 1 and e["asunto"] == smtp.enviados[0]["Subject"]
    assert e["resumen"] == vp["texto"] and "semana siguiente" in e["asunto"]
    # algo dentro del período normal: sale solo eso, sin adelanto
    v = vehiculo(api, "AAA123", cl["id"])   # sin seguro
    vp = ok(api.get("/api/mail/vista-previa"))
    assert (vp["adelanto"], vp["cantidad_alertas"]) == (False, 1) and "AAA123" in vp["texto"] and "L-1" not in vp["texto"]
    ok(api.post(f"/api/vehiculos/{v['id']}/baja"))
    # tampoco en la semana extendida: "sin vencimientos próximos"
    ok(api.put(f"/api/documentos/{d['id']}", json={"tipo_id": d["tipo_id"], "numero": "L-1",
                                                   "vencimiento": (datetime.now().date() + timedelta(days=38)).isoformat()}))
    vp = ok(api.get("/api/mail/vista-previa"))
    assert (vp["adelanto"], vp["cantidad_alertas"]) == (False, 0) and "sin vencimientos próximos" in vp["asunto"]


def test_sin_la_clave_de_cifrado_no_es_un_500(api, smtp):
    """Si data/clave_secretos.key falta (se copió solo la base), el envío queda registrado con el aviso de volver a
    cargar la contraseña, la prueba da 400 con ese mensaje y nada se manda."""
    configurar(api)
    secretos.ruta_clave().unlink()
    e = correo.revisar(datetime(2026, 11, 9, 8, 0))
    assert e["resultado"] == "error" and "Volvé a cargar la contraseña del mail" in e["error"]
    assert "Volvé a cargar" in error(api.post("/api/mail/prueba", json={}))
    assert smtp.enviados == []
    ok(api.patch("/api/opciones", json={"smtp_password": "clave-inventada"}))
    assert ok(api.post("/api/mail/prueba", json={}))["resultado"] == "ok"
    assert smtp.instancias[-1].acciones[-1] == ("login", "cuenta@ejemplo.com", "clave-inventada")
