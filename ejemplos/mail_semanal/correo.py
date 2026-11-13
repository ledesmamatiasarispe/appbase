"""Resumen semanal por mail al productor: arma el mail con las alertas, lo manda por SMTP y lleva el registro.

CUÁNDO: una vez por semana, el día y la hora de Opciones (lunes 08:00 por defecto). El PERÍODO es el último momento
programado que ya pasó (periodo()). El programador (un hilo de fondo que arranca en el lifespan de main.py) mira
cada INTERVALO_S segundos si ese período ya tiene un envío semanal exitoso; si no, lo manda. Así:
  - si la app estaba apagada a la hora programada, sale al arrancar (un solo mail, aunque hayan pasado semanas);
  - no se manda dos veces lo mismo: cuenta cualquier envío semanal exitoso hecho DESPUÉS del momento programado
    (por eso cambiar el día o la hora no dispara un mail repetido), y el índice único de envios_mail por período es
    el respaldo;
  - si falla (servidor caído, contraseña mal), queda registrado con el error y se reintenta a los REINTENTO_MIN minutos.
Sin cuenta SMTP o sin destinatarios no se intenta nada (ni se registra). AUTO_MAIL=0 apaga el programador (los tests).

QUÉ: todas las alertas de alertas.py (vencidas, urgentes, próximas), en texto y en HTML simple. Si en el período
normal no hay ninguna (decisión del usuario), se EXTIENDE EL RANGO UNA SEMANA MÁS (EXTENSION_DIAS sumados a "aparece"
de cada tipo) y sale lo que aparezca ahí, aclarando que es lo que viene después; si aun así no hay nada, sale igual
con "sin vencimientos próximos": así el productor sabe que el aviso funciona. alertas_del_resumen() es la única que
decide eso: la usan el envío semanal, la prueba y la vista previa.

CONTRASEÑA: se guarda cifrada (opciones.password_smtp la descifra). Si no se puede descifrar (falta la clave en
data/), el envío queda registrado con ese error ("volvé a cargar la contraseña del mail") y la prueba da 400.

REGISTRO (envios_mail, append-only como el historial): cuándo, tipo (semanal/prueba), período, quién (Sistema en
los automáticos), a quién, asunto, resultado, error, cantidad de alertas y el texto que se mandó.

El mail se manda FUERA de la transacción (puede tardar hasta TIMEOUT_S y no tiene que frenar a los demás usuarios);
un candado del proceso evita que dos revisiones se pisen.
"""
import html
import json
import logging
import os
import smtplib
import ssl
import threading
from datetime import datetime, time, timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from . import alertas as al, opciones
from .db import transaccion
from .servicios import SISTEMA, ErrorDeNegocio, _mail
from .version import NOMBRE

INTERVALO_S = 60
REINTENTO_MIN = 60
TIMEOUT_S = 30
_TITULOS = {"vencida": "Vencidas", "urgente": "Urgentes", "proxima": "Próximas"}
EXTENSION_DIAS = 7
_TIPOS = {"vigencia": "Fin de vigencia", "cuota": "Cuota / refacturación", "documentacion": "Documentación",
          "sin_seguro": "Sin seguro"}
_candado = threading.Lock()
log = logging.getLogger(__name__)


# ── lógica pura ─────────────────────────────────────────────────────────────

def periodo(ahora: datetime, dia: str, hora: str) -> datetime:
    """El último momento programado (día de la semana + hora) que ya llegó: el período que tiene que estar mandado."""
    h, m = (int(x) for x in hora.split(":"))
    atras = (ahora.weekday() - opciones.DIAS_SEMANA.index(dia)) % 7
    candidato = datetime.combine(ahora.date() - timedelta(days=atras), time(h, m))
    return candidato if candidato <= ahora else candidato - timedelta(days=7)


def texto_adelanto(dias: int = EXTENSION_DIAS) -> str:
    return (f"No hay vencimientos en el período habitual de aviso. Esto es lo que viene después, en los {dias} días "
            "siguientes:")


def armar(alertas: list[dict], hoy: str, prueba: bool = False, adelanto: bool = False) -> dict:
    """{asunto, texto, html} del resumen. Las alertas ya vienen ordenadas (alertas.ordenar).
    adelanto: son las de la semana extendida (el período normal no tenía nada)."""
    fecha = al._dmy(hoy)
    n = len(alertas)
    if not alertas:
        que = "sin vencimientos próximos"
    elif adelanto:
        que = f"sin vencimientos en el período habitual; {n} en la semana siguiente"
    else:
        que = f"{n} vencimiento{'s' if n != 1 else ''} para revisar"
    asunto = f"{'[PRUEBA] ' if prueba else ''}{NOMBRE}: {que} ({fecha})"
    texto = [f"Resumen de vencimientos al {fecha}", ""]
    cuerpo = [f"<h2 style=\"font-family:sans-serif;color:#17324d\">Resumen de vencimientos al {fecha}</h2>"]
    if not alertas:
        texto.append("No hay vencimientos próximos ni vencidos.")
        cuerpo.append("<p style=\"font-family:sans-serif\">No hay vencimientos próximos ni vencidos.</p>")
    elif adelanto:
        texto += [texto_adelanto(), ""]
        cuerpo.append(f"<p style=\"font-family:sans-serif\">{html.escape(texto_adelanto())}</p>")
    for nivel, titulo in _TITULOS.items():
        grupo = [a for a in alertas if a["nivel"] == nivel]
        if not grupo:
            continue
        texto += [f"{titulo.upper()} ({len(grupo)})"] + [f"  - [{_TIPOS[a['tipo']]}] {a['texto']}" for a in grupo] + [""]
        filas = "".join(f"<tr><td style=\"padding:4px 8px;white-space:nowrap\">{html.escape(_TIPOS[a['tipo']])}</td>"
                        f"<td style=\"padding:4px 8px\">{html.escape(a['texto'])}</td></tr>" for a in grupo)
        cuerpo.append(f"<h3 style=\"font-family:sans-serif\">{titulo} ({len(grupo)})</h3>"
                      f"<table style=\"font-family:sans-serif;font-size:14px;border-collapse:collapse\" border=\"1\">{filas}</table>")
    pie = f"Mail automático de {NOMBRE}."
    texto.append(pie)
    cuerpo.append(f"<p style=\"font-family:sans-serif;color:#777;font-size:12px\">{html.escape(pie)}</p>")
    return {"asunto": asunto, "texto": "\n".join(texto), "html": "<html><body>" + "".join(cuerpo) + "</body></html>"}


# ── envío ───────────────────────────────────────────────────────────────────

def _exigir_cuenta(op: dict) -> None:
    if not op["smtp_servidor"]:
        raise ErrorDeNegocio("Falta configurar el servidor SMTP en Opciones.")
    if not (op["smtp_remitente"] or op["smtp_usuario"]):
        raise ErrorDeNegocio("Falta configurar el remitente (o el usuario) de la cuenta de mail en Opciones.")


def enviar(op: dict, destinatarios: list[str], armado: dict) -> None:
    """Manda el mail con la cuenta de Opciones (op con la contraseña YA descifrada). Lanza la excepción de
    smtplib/ssl/socket si falla."""
    msg = EmailMessage()
    msg["Subject"] = armado["asunto"]
    msg["From"] = op["smtp_remitente"] or op["smtp_usuario"]
    msg["To"] = ", ".join(destinatarios)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(armado["texto"])
    msg.add_alternative(armado["html"], subtype="html")
    contexto = ssl.create_default_context()
    if op["smtp_seguridad"] == "ssl":
        servidor = smtplib.SMTP_SSL(op["smtp_servidor"], op["smtp_puerto"], timeout=TIMEOUT_S, context=contexto)
    else:
        servidor = smtplib.SMTP(op["smtp_servidor"], op["smtp_puerto"], timeout=TIMEOUT_S)
    with servidor as s:
        if op["smtp_seguridad"] == "tls":
            s.starttls(context=contexto)
        if op["smtp_usuario"]:
            s.login(op["smtp_usuario"], op["smtp_password"])
        s.send_message(msg)


def _registrar_envio(usuario: dict, tipo: str, per: str | None, destinatarios: list[str], armado: dict, cantidad: int,
                     error: str, cuando: datetime) -> dict:
    with transaccion() as c:
        nuevo = c.execute(
            "INSERT INTO envios_mail (cuando, tipo, periodo, legajo, usuario, destinatarios, asunto, resultado, error, "
            "cantidad_alertas, resumen) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (cuando.isoformat(timespec="seconds"), tipo, per, usuario.get("legajo"), usuario["nombre"],
             json.dumps(destinatarios, ensure_ascii=False), armado["asunto"], "error" if error else "ok", error, cantidad,
             armado["texto"])).lastrowid
        return _envio(c.execute("SELECT * FROM envios_mail WHERE id=?", (nuevo,)).fetchone())


def alertas_del_resumen(hoy: str) -> tuple[list[dict], bool]:
    """(alertas, adelanto). Las del período normal; si no hay ninguna, las de una semana más (adelanto = True)."""
    lista = al.listar(hoy=hoy)
    if lista:
        return lista, False
    extendida = al.listar(hoy=hoy, extra=EXTENSION_DIAS)
    return extendida, bool(extendida)


def _mandar(usuario: dict, tipo: str, per: str | None, op: dict, destinatarios: list[str], ahora: datetime) -> dict:
    hoy = ahora.date().isoformat()
    lista, adelanto = alertas_del_resumen(hoy)
    armado = armar(lista, hoy, prueba=tipo == "prueba", adelanto=adelanto)
    try:
        enviar({**op, "smtp_password": opciones.password_smtp(op)}, destinatarios, armado)
        error = ""
    except ErrorDeNegocio as e:   # la contraseña guardada no se puede descifrar
        error = str(e)
        log.warning("No se pudo mandar el resumen por mail: %s", error)
    except (smtplib.SMTPException, OSError, ssl.SSLError, ValueError) as e:
        error = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        log.warning("No se pudo mandar el resumen por mail: %s", error)
    return _registrar_envio(usuario, tipo, per, destinatarios, armado, len(lista), error, ahora)


def mandar_prueba(usuario: dict, *, mail=None) -> dict:
    """El resumen de hoy, marcado [PRUEBA], a `mail` si viene o a la lista de destinatarios. Queda registrado aunque
    falle; si falla, el error se le muestra al usuario (400)."""
    with transaccion() as c:
        op = opciones._leer(c)
    _exigir_cuenta(op)
    destinatarios = [_mail(mail, "el mail de prueba", obligatorio=True)] if mail not in (None, "") else op["mail_destinatarios"]
    if not destinatarios:
        raise ErrorDeNegocio("No hay destinatarios: cargar al menos un mail en Opciones (o uno para la prueba).")
    envio = _mandar(usuario, "prueba", None, op, destinatarios, datetime.now())
    if envio["resultado"] != "ok":
        raise ErrorDeNegocio(f"No se pudo mandar el mail ({envio['error']}). Revisar la cuenta SMTP en Opciones.")
    return envio


def revisar(ahora: datetime | None = None) -> dict | None:
    """Una vuelta del programador: manda el resumen del período si corresponde. Devuelve el envío registrado, o None
    si no tocaba (ya salió, todavía no hay que reintentar, o el mail no está configurado)."""
    ahora = ahora or datetime.now()
    with _candado:
        with transaccion() as c:
            op = opciones._leer(c)
            if not (op["smtp_servidor"] and (op["smtp_remitente"] or op["smtp_usuario"]) and op["mail_destinatarios"]):
                return None
            momento = periodo(ahora, op["resumen_dia"], op["resumen_hora"])
            per = momento.isoformat(timespec="minutes")
            if c.execute("SELECT 1 FROM envios_mail WHERE tipo='semanal' AND resultado='ok' AND (cuando >= ? OR periodo = ?)",
                         (per, per)).fetchone():
                return None
            reintento = (ahora - timedelta(minutes=REINTENTO_MIN)).isoformat(timespec="seconds")
            if c.execute("SELECT 1 FROM envios_mail WHERE tipo='semanal' AND periodo=? AND resultado='error' AND cuando > ?",
                         (per, reintento)).fetchone():
                return None
        return _mandar(SISTEMA, "semanal", per, op, op["mail_destinatarios"], ahora)


# ── programador (hilo de fondo) ─────────────────────────────────────────────

_parar: threading.Event | None = None


def _bucle(parar: threading.Event) -> None:
    while True:
        try:
            revisar()
        except Exception:   # el hilo no se puede morir por un error: lo deja en el log y sigue en la próxima vuelta
            log.exception("Error en el programador del resumen semanal")
        if parar.wait(INTERVALO_S):
            return


def programador_activo() -> bool:
    return os.environ.get("AUTO_MAIL", "1") != "0"


def iniciar_programador() -> bool:
    """Lo llama el lifespan de main.py. AUTO_MAIL=0 lo deja apagado (y entonces solo se manda la prueba a mano)."""
    global _parar
    if not programador_activo() or _parar is not None:
        return False
    _parar = threading.Event()
    threading.Thread(target=_bucle, args=(_parar,), name="resumen-semanal", daemon=True).start()
    return True


def detener_programador() -> None:
    global _parar
    if _parar is not None:
        _parar.set()
        _parar = None


# ── consultas ───────────────────────────────────────────────────────────────

def _envio(r) -> dict:
    return {**dict(r), "destinatarios": json.loads(r["destinatarios"])}


def envios(limite=50) -> list[dict]:
    try:
        limite = max(1, min(int(limite), 500))
    except (TypeError, ValueError):
        limite = 50
    with transaccion() as c:
        return [_envio(r) for r in c.execute("SELECT * FROM envios_mail ORDER BY id DESC LIMIT ?", (limite,))]


def vista_previa(hoy: str | None = None) -> dict:
    """El resumen tal como saldría hoy (sin mandarlo), con la misma extensión de una semana si no hay nada."""
    hoy = hoy or datetime.now().date().isoformat()
    lista, adelanto = alertas_del_resumen(hoy)
    return {**armar(lista, hoy, adelanto=adelanto), "cantidad_alertas": len(lista), "adelanto": adelanto}


def estado(ahora: datetime | None = None) -> dict:
    ahora = ahora or datetime.now()
    with transaccion() as c:
        op = opciones._leer(c)
        ultimo = c.execute("SELECT * FROM envios_mail WHERE tipo='semanal' ORDER BY id DESC LIMIT 1").fetchone()
        momento = periodo(ahora, op["resumen_dia"], op["resumen_hora"])
        per = momento.isoformat(timespec="minutes")
        hecho = c.execute("SELECT 1 FROM envios_mail WHERE tipo='semanal' AND resultado='ok' AND (cuando >= ? OR periodo = ?)",
                          (per, per)).fetchone()
    configurado = opciones._publicas(op)["mail_configurado"]
    return {"programador_activo": programador_activo(), "configurado": configurado,
            "resumen_dia": op["resumen_dia"], "resumen_hora": op["resumen_hora"],
            "proximo": (momento + timedelta(days=7) if hecho else momento).isoformat(timespec="minutes") if configurado else None,
            "ultimo_envio": _envio(ultimo) if ultimo else None}
