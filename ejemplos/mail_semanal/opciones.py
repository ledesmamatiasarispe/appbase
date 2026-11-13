"""Opciones globales del sistema (tabla config, clave -> valor JSON): ritmo de las alertas, destinatarios y cuenta
del mail semanal, día y hora del resumen.

Son UNA configuración para toda la instalación (no por póliza ni por compañía). Las lee cualquiera que necesite
un aviso a través de _leer(c), que completa con los valores por defecto lo que nunca se configuró. Las escribe solo
un administrador (main.py), y cada cambio queda en el historial (entidad "opciones", id 1) con la contraseña
enmascarada.

CUOTAS (decisión del usuario, 2026-11-04): avisar_cuotas prende o apaga JUNTAS las alertas de vencimiento de cuota
(y por lo tanto su renglón en el mail) y sus eventos en el cronograma. Apagado por defecto. Apagado no toca las
cuotas en sí: la ficha de la póliza las sigue mostrando y ahí se registran los pagos.

RITMO DE LAS ALERTAS (decisión del usuario, 2026-11-04; reemplaza la lista escalonada 30/15/7 de vigencia): cada
tipo tiene "aparece N días antes" (aviso_<tipo>) y "se pone roja / urgente cuando faltan M días o menos"
(urgente_<tipo>), con M <= N. La alerta se muestra TODOS los días desde N. ritmo(op, tipo) es el ÚNICO lugar donde
se leen esos dos números: lo usan alertas.py (niveles), polizas.py (estado "por_vencer" = faltan <= N de vigencia),
documentacion.py (estado "por_vencer" = faltan <= N de documentación) y, a través de alertas, el mail.

CONTRASEÑA SMTP: CIFRADA (secretos.py, clave en un archivo aparte de data/) y NUNCA sale por la API: leer() solo dice
si está cargada y si se puede leer. Al guardar, vacía = dejar la que estaba; para sacarla, smtp_password_borrar.
password_smtp(op) la descifra para mandar el mail.

MIGRACIÓN (migrar(c), la llama db.inicializar al arrancar; idempotente): la lista vieja avisos_vigencia pasa a
aviso_vigencia = su mayor valor, y una contraseña en texto plano de una versión anterior se cifra. Las dos dejan su
renglón en el historial (usuario Sistema, acción "migracion").
"""
import json
import re
import unicodedata

from . import secretos
from .db import transaccion
from .servicios import SISTEMA, ErrorDeNegocio, _mail, _numero, _opcion, _registrar, _texto

DIAS_SEMANA = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")   # índice = date.weekday()
SEGURIDADES = ("tls", "ssl", "ninguna")   # tls = STARTTLS (puerto 587), ssl = SMTP sobre SSL (465)
MAX_DIAS_AVISO = 365

DEFECTOS = {
    "aviso_vigencia": 15,               # la alerta de fin de vigencia aparece 15 días antes (usuario)
    "urgente_vigencia": 3,              # ...y se pone roja cuando faltan 3 o menos (usuario)
    "avisar_cuotas": False,             # alertas y cronograma de cuotas: apagado por defecto (usuario)
    "aviso_cuota": 7,                   # cuota / refacturación (el N de siempre)
    "urgente_cuota": 3,                 # (decidido acá, igual que vigencia)
    "aviso_documentacion": 30,          # documentación (el N de siempre)
    "urgente_documentacion": 3,         # (decidido acá, igual que vigencia)
    "mail_destinatarios": [],
    "smtp_servidor": "",
    "smtp_puerto": 587,
    "smtp_usuario": "",
    "smtp_password": "",                # CIFRADA ("fernet:..."); nunca sale por la API
    "smtp_remitente": "",
    "smtp_seguridad": "tls",
    "resumen_dia": "lunes",
    "resumen_hora": "08:00",
}
CLAVES = tuple(DEFECTOS) + ("smtp_password_borrar",)
# tipo de alerta -> (clave de "aparece N días antes", clave de "urgente cuando faltan M o menos")
RITMOS = {"vigencia": ("aviso_vigencia", "urgente_vigencia"), "cuota": ("aviso_cuota", "urgente_cuota"),
          "documentacion": ("aviso_documentacion", "urgente_documentacion")}
_NOMBRES = {"vigencia": "fin de vigencia", "cuota": "cuota / refacturación", "documentacion": "documentación"}


def _leer(c) -> dict:
    """Todas las opciones (con la contraseña CIFRADA), con el defecto en lo que no se configuró o quedó ilegible."""
    guardado = {r["clave"]: r["valor"] for r in c.execute(
        f"SELECT clave, valor FROM config WHERE clave IN ({','.join('?' * len(DEFECTOS))})", tuple(DEFECTOS))}
    op = {}
    for clave, defecto in DEFECTOS.items():
        try:
            valor = json.loads(guardado[clave]) if clave in guardado else defecto
        except ValueError:
            valor = defecto
        op[clave] = valor if type(valor) is type(defecto) else defecto   # type, no isinstance: True no es un número
    for aviso, urgente in RITMOS.values():   # un número mal guardado a mano no puede dejar sin avisos
        if not 1 <= op[aviso] <= MAX_DIAS_AVISO:
            op[aviso] = DEFECTOS[aviso]
        if not 0 <= op[urgente] <= MAX_DIAS_AVISO:
            op[urgente] = DEFECTOS[urgente]
    return op


def ritmo(op: dict, tipo: str) -> tuple[int, int]:
    """(aparece N días antes, urgente cuando faltan M o menos) del tipo de alerta. M nunca pasa de N."""
    aviso, urgente = RITMOS[tipo]
    return op[aviso], min(op[urgente], op[aviso])


def password_smtp(op: dict) -> str:
    """La contraseña SMTP en claro, para mandar el mail. ErrorDeNegocio si no se puede descifrar."""
    return secretos.descifrar(op["smtp_password"])


def _publicas(op: dict) -> dict:
    sin = {k: v for k, v in op.items() if k != "smtp_password"}
    return {**sin, "smtp_password_cargada": bool(op["smtp_password"]),
            "smtp_password_error": secretos.error_de_lectura(op["smtp_password"]),
            "mail_configurado": bool(op["smtp_servidor"] and op["mail_destinatarios"] and (op["smtp_remitente"] or op["smtp_usuario"]))}


def leer() -> dict:
    with transaccion() as c:
        return _publicas(_leer(c))


# ── validación ──────────────────────────────────────────────────────────────

def _lista(valor) -> list:
    """Lista que viene de la pantalla como lista JSON o como texto separado por comas, punto y coma o renglones."""
    if valor is None:
        return []
    if isinstance(valor, (list, tuple)):
        return list(valor)
    return [x for x in re.split(r"[,;\s]+", str(valor)) if x]


def _dias(valor, campo: str, minimo: int = 1) -> int:
    n = _numero(valor, campo, entero=True, minimo=minimo, maximo=MAX_DIAS_AVISO)
    if n is None:
        raise ErrorDeNegocio(f"Falta {campo}.")
    return n


def _destinatarios(valor) -> list[str]:
    mails = []
    for m in _lista(valor):
        m = _mail(m, "el mail destinatario", obligatorio=True)
        if m in mails:
            raise ErrorDeNegocio(f"El mail {m} está repetido en la lista de destinatarios.")
        mails.append(m)
    return mails


def _sin_acentos(t: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", t) if unicodedata.category(ch) != "Mn")


def _si_no(valor, campo: str) -> bool:
    if isinstance(valor, bool):
        return valor
    t = _sin_acentos(str(valor if valor is not None else "").strip().lower())
    if t in ("1", "true", "si", "on"):
        return True
    if t in ("0", "false", "no", "off", ""):
        return False
    raise ErrorDeNegocio(f"{campo}: '{valor}' no es sí ni no.")


def _hora(valor) -> str:
    t = _texto(valor, "la hora del resumen")
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?", t)
    if not m or int(m[1]) > 23 or int(m[2] or 0) > 59:
        raise ErrorDeNegocio(f"La hora del resumen: '{t}' no es una hora (HH:MM, de 00:00 a 23:59).")
    return f"{int(m[1]):02d}:{int(m[2] or 0):02d}"


_VALIDAR = {
    "mail_destinatarios": _destinatarios,
    "smtp_servidor": lambda v: _texto(v, "", False),
    "smtp_puerto": lambda v: _numero(v, "el puerto SMTP", entero=True, minimo=1, maximo=65535) or DEFECTOS["smtp_puerto"],
    "smtp_usuario": lambda v: _texto(v, "", False),
    "smtp_remitente": lambda v: _mail(v, "el remitente"),
    "smtp_seguridad": lambda v: _opcion(str(v or "").strip().lower(), list(SEGURIDADES), "la seguridad SMTP"),
    "resumen_dia": lambda v: _opcion(_sin_acentos(str(v or "").strip().lower()), list(DIAS_SEMANA), "el día del resumen"),
    "resumen_hora": _hora,
    "avisar_cuotas": lambda v: _si_no(v, "Avisar los vencimientos de cuota"),
}
for _tipo, (_aviso, _urgente) in RITMOS.items():
    _VALIDAR[_aviso] = lambda v, t=_tipo: _dias(v, f"los días antes en que aparece la alerta de {_NOMBRES[t]}")
    _VALIDAR[_urgente] = lambda v, t=_tipo: _dias(v, f"los días en que la alerta de {_NOMBRES[t]} pasa a urgente", 0)


def _exigir_ritmos(op: dict) -> None:
    for tipo, (aviso, urgente) in RITMOS.items():
        if op[urgente] > op[aviso]:
            raise ErrorDeNegocio(f"Alerta de {_NOMBRES[tipo]}: pasa a urgente cuando faltan {op[urgente]} días o menos, "
                                 f"pero aparece {op[aviso]} días antes. El primer número no puede ser mayor que el segundo.")


def _escribir(c, clave: str, valor) -> None:
    c.execute("INSERT INTO config (clave, valor) VALUES (?, ?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
              (clave, json.dumps(valor, ensure_ascii=False)))


def _misma_password(cifrada: str, nueva: str) -> bool:
    try:
        return secretos.descifrar(cifrada) == nueva
    except ErrorDeNegocio:   # la guardada no se puede leer: la nueva la reemplaza
        return False


def guardar(usuario: dict, **datos) -> dict:
    """Cambia SOLO las opciones que vienen (la pantalla puede guardar una sección por vez). Todo se valida antes de
    escribir: si una falla, no se guarda ninguna. El par aparece/urgente de cada alerta se valida con el valor que
    queda guardado del otro (se puede mandar uno solo). Deja en el historial lo que cambió."""
    nuevas = {k: _VALIDAR[k](v) for k, v in datos.items() if k in _VALIDAR}
    password = None
    if datos.get("smtp_password_borrar"):
        password = ""
    elif datos.get("smtp_password") not in (None, ""):
        password = str(datos["smtp_password"])
    with transaccion() as c:
        actual = _leer(c)
        _exigir_ritmos({**actual, **nuevas})
        cambios = {k: v for k, v in nuevas.items() if actual[k] != v}
        if password is not None and not (password == "" and not actual["smtp_password"]) \
                and not (password and _misma_password(actual["smtp_password"], password)):
            cambios["smtp_password"] = secretos.cifrar(password)
        for k, v in cambios.items():
            _escribir(c, k, v)
        if cambios:
            def mascara(k, v):
                return ("(cargada)" if v else "(vacía)") if k == "smtp_password" else v
            _registrar(c, usuario, "opciones", 1, "edicion", {k: mascara(k, actual[k]) for k in cambios},
                       {k: mascara(k, v) for k, v in cambios.items()})
        return _publicas(_leer(c))


# ── migración al arrancar ───────────────────────────────────────────────────

def migrar(c) -> None:
    """Idempotente (la llama db.inicializar en cada arranque; si no hay nada viejo, no hace nada).
    - avisos_vigencia (lista escalonada, p. ej. [30, 15, 7]) -> aviso_vigencia = el mayor, salvo que aviso_vigencia
      ya esté guardado; la clave vieja se borra. Si el nuevo N queda por debajo del urgente, el urgente baja a N.
    - smtp_password en texto plano -> cifrada."""
    guardado = {r["clave"]: r["valor"] for r in c.execute(
        "SELECT clave, valor FROM config WHERE clave IN ('avisos_vigencia', 'aviso_vigencia', 'smtp_password')")}
    if "avisos_vigencia" in guardado:
        try:
            viejos = [int(d) for d in json.loads(guardado["avisos_vigencia"]) if 1 <= int(d) <= MAX_DIAS_AVISO]
        except (TypeError, ValueError):
            viejos = []
        despues = {}
        if viejos and "aviso_vigencia" not in guardado:
            despues["aviso_vigencia"] = max(viejos)
            _escribir(c, "aviso_vigencia", max(viejos))
            if _leer(c)["urgente_vigencia"] > max(viejos):
                despues["urgente_vigencia"] = max(viejos)
                _escribir(c, "urgente_vigencia", max(viejos))
        c.execute("DELETE FROM config WHERE clave='avisos_vigencia'")
        _registrar(c, SISTEMA, "opciones", 1, "migracion", {"avisos_vigencia": viejos}, despues or None)
    if "smtp_password" in guardado:
        try:
            valor = json.loads(guardado["smtp_password"])
        except ValueError:
            valor = ""
        if isinstance(valor, str) and valor and not secretos.esta_cifrado(valor):
            c.execute("PRAGMA secure_delete = ON")   # que el texto plano no quede en el espacio libre del archivo
            _escribir(c, "smtp_password", secretos.cifrar(valor))
            _registrar(c, SISTEMA, "opciones", 1, "migracion", {"smtp_password": "(texto plano)"},
                       {"smtp_password": "(cifrada)"})
