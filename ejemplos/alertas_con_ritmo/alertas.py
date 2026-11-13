"""Alertas: lo que vence hoy, pronto o ya venció. Es el panel de Inicio y el contenido del mail semanal.

RITMO (opciones.ritmo, una sola configuración para todos): cada tipo APARECE N días antes y se muestra TODOS los
días desde ahí (no en escalones), y pasa a URGENTE (roja) cuando faltan M días o menos (M <= N).
Por defecto: vigencia N=15, M=3 (usuario); cuota N=7, M=3; documentación N=30, M=3.

Cuatro tipos:
  vigencia       fin de vigencia de una póliza no anulada y sin renovar. No avisa si otra póliza ya cubre lo mismo
                 desde ese día (una renovación cargada como póliza nueva, una flota). Una vencida sin renovar se
                 muestra VENCIDAS_VISIBLES días más; después lo que queda a la vista es el vehículo "sin seguro".
  cuota          próxima cuota impaga (vencimiento_cuota de la póliza). Vencida sigue avisando hasta que se carga el
                 pago (desde la alerta, con poliza_id). Con frecuencia de refacturación el texto dice "refacturación".
  documentacion  documentos actuales (activos, sin renovar, de un dueño activo). Vencido sigue avisando hasta que
                 se renueva o se da de baja.
  sin_seguro     vehículo activo sin ninguna póliza que lo cubra hoy (los cubiertos por la póliza de su flota no
                 cuentan). Siempre nivel "vencida".

UNA SOLA ALERTA POR VEHÍCULO al vencer el seguro (decisión del usuario): mientras se ve la alerta de vigencia vencida
de la póliza con la que terminó su última cobertura (VENCIDAS_VISIBLES días), el vehículo NO tiene además la de "sin
seguro": la de vigencia es la que tiene la acción (renovar) y ya dice que quedó sin seguro. Pasado ese plazo, o si
nunca tuvo póliza, o si su última cobertura no terminó con la póliza (salió de la flota), queda "sin seguro".

NIVEL: vencida (vigencia: desde el día "hasta", que ya no cubre; cuotas y documentos: desde el día siguiente al
vencimiento) > urgente (faltan <= M; para vigencia, 0 < días <= M) > proxima.

Las funciones alerta_* son PURAS (reciben filas como dict, la fecha de hoy y el ritmo): las prueba
tests/test_alertas.py sin base. listar() junta los datos en una transacción y las aplica.
"""
from datetime import date

from . import documentacion, opciones, polizas
from .db import transaccion
from .servicios import _hoy, _opcion

TIPOS = ("vigencia", "cuota", "documentacion", "sin_seguro")
NIVELES = ("vencida", "urgente", "proxima")
VENCIDAS_VISIBLES = 30
_dmy = polizas._dmy


def _dias(fecha: str, hoy: str) -> int:
    return (date.fromisoformat(fecha) - date.fromisoformat(hoy)).days


def _cuando(dias: int) -> str:
    if dias == 0:
        return "hoy"
    if dias < 0:
        return f"hace {-dias} día{'s' if dias != -1 else ''}"
    return f"en {dias} día{'s' if dias != 1 else ''}"


def _alerta(tipo, fecha, dias, nivel, entidad, entidad_id, texto, **extra) -> dict:
    base = {"tipo": tipo, "fecha": fecha, "dias": dias, "nivel": nivel, "entidad": entidad, "entidad_id": entidad_id,
            "texto": texto, "poliza_id": None, "documento_id": None, "vehiculo_id": None, "flota_id": None,
            "cliente_id": None, "dominio": None, "cliente": None, "aviso": None, "urgente_desde": None}
    return {**base, **extra}


def _nivel(dias: int, urgente: int, vencida: bool) -> str:
    return "vencida" if vencida else "urgente" if dias <= urgente else "proxima"


def alerta_vigencia(p: dict, hoy: str, aparece: int, urgente: int, sucedida: bool = False) -> dict | None:
    """p: una póliza de polizas._listar. sucedida: otra póliza ya cubre lo mismo desde el día en que esta termina."""
    if p["anulada"] or p["renovada_por_id"] or sucedida:
        return None
    dias = _dias(p["vigencia_hasta"], hoy)
    if dias > aparece or -dias > VENCIDAS_VISIBLES:
        return None
    quien = f"póliza {p['numero']} de {p['compania']} ({polizas.que_cubre(p)}, {p['cliente']})"
    if dias <= 0:
        tipo = polizas.tipo(p)
        sin = {"vehiculo": "el vehículo quedó sin seguro", "flota": "los vehículos de la flota quedaron sin seguro",
               "personal": "el cliente quedó sin esa cobertura"}.get(tipo, f"el {tipo} quedó sin seguro")
        texto = (f"Terminó la vigencia de la {quien} el {_dmy(p['vigencia_hasta'])} ({_cuando(dias)}) y no tiene "
                 f"renovación: {sin}.")
    else:
        texto = f"Vence la {quien} el {_dmy(p['vigencia_hasta'])} ({_cuando(dias)})."
    return _alerta("vigencia", p["vigencia_hasta"], dias, _nivel(dias, urgente, dias <= 0), "poliza", p["id"], texto,
                   poliza_id=p["id"], vehiculo_id=p["vehiculo_id"], flota_id=p["flota_id"], cliente_id=p["cliente_id"],
                   dominio=p["dominio"], cliente=p["cliente"], aviso=aparece, urgente_desde=urgente)


def alerta_cuota(p: dict, hoy: str, aparece: int, urgente: int) -> dict | None:
    if p["anulada"] or p["proxima_cuota"] is None or not p["vencimiento_cuota"]:
        return None
    dias = _dias(p["vencimiento_cuota"], hoy)
    if dias > aparece:
        return None
    que = "Refacturación" if p["frecuencia_refacturacion"] != "ninguna" else "Cuota"
    verbo = "venció" if dias < 0 else "vence"
    texto = (f"{que} (cuota {p['proxima_cuota']} de {p['cantidad_cuotas']}) de la póliza {p['numero']} de "
             f"{p['compania']} ({polizas.que_cubre(p)}, {p['cliente']}): {verbo} el {_dmy(p['vencimiento_cuota'])} ({_cuando(dias)}).")
    return _alerta("cuota", p["vencimiento_cuota"], dias, _nivel(dias, urgente, dias < 0), "poliza", p["id"], texto,
                   poliza_id=p["id"], vehiculo_id=p["vehiculo_id"], flota_id=p["flota_id"], cliente_id=p["cliente_id"],
                   dominio=p["dominio"], cliente=p["cliente"], aviso=aparece, urgente_desde=urgente,
                   numero_cuota=p["proxima_cuota"])


def alerta_documento(d: dict, hoy: str, aparece: int, urgente: int) -> dict | None:
    """d: un documento actual de documentacion._listar."""
    if not d["activo"] or d["renovado_por_id"]:
        return None
    dias = _dias(d["vencimiento"], hoy)
    if dias > aparece:
        return None
    verbo = "venció" if dias < 0 else "vence"
    numero = f" n.º {d['numero']}" if d.get("numero") else ""
    texto = f"{d['tipo']}{numero} de {d['titular']}: {verbo} el {_dmy(d['vencimiento'])} ({_cuando(dias)})."
    return _alerta("documentacion", d["vencimiento"], dias, _nivel(dias, urgente, dias < 0), "documento", d["id"], texto,
                   documento_id=d["id"], vehiculo_id=d["vehiculo_id"], cliente_id=d["cliente_id"], dominio=d["dominio"],
                   cliente=d["cliente"], aviso=aparece, urgente_desde=urgente)


def alerta_sin_seguro(v: dict, hoy: str, ultima_hasta: str | None, proxima_desde: str | None) -> dict:
    """v: {id, dominio, cliente_id, cliente}. ultima_hasta: fin de su última cobertura (None = nunca tuvo);
    proxima_desde: inicio de una cobertura ya cargada que todavía no empezó."""
    duenio = f" ({v['cliente']})" if v.get("cliente") else ""
    if ultima_hasta:
        texto = f"{v['dominio']}{duenio} no tiene seguro vigente: la última cobertura terminó el {_dmy(ultima_hasta)}"
    else:
        texto = f"{v['dominio']}{duenio} no tiene seguro vigente: nunca tuvo una póliza cargada"
    if proxima_desde:
        texto += f"; la próxima empieza el {_dmy(proxima_desde)}"
    return _alerta("sin_seguro", ultima_hasta, _dias(ultima_hasta, hoy) if ultima_hasta else None, "vencida", "vehiculo",
                   v["id"], texto + ".", vehiculo_id=v["id"], cliente_id=v.get("cliente_id"), dominio=v["dominio"],
                   cliente=v.get("cliente"))


def ordenar(alertas: list[dict]) -> list[dict]:
    """Primero las vencidas, después las urgentes y las próximas; dentro de cada nivel, la más cercana primero."""
    return sorted(alertas, key=lambda a: (NIVELES.index(a["nivel"]), a["dias"] if a["dias"] is not None else -10**6,
                                          TIPOS.index(a["tipo"]), a["texto"]))


# ── con la base ─────────────────────────────────────────────────────────────

def _sucedida(p: dict, coberturas: list[dict], pols: list[dict]) -> bool:
    """¿Otra póliza ya cubre lo mismo desde el día en que esta termina? (cargada como nueva, no como renovación)."""
    h = p["vigencia_hasta"]
    if polizas.tipo(p) not in ("vehiculo", "flota"):   # personales y bienes: varias a la vez, solo la sucede su renovación
        return False
    if p["vehiculo_id"]:
        return any(cob["vehiculo_id"] == p["vehiculo_id"] and cob["poliza_id"] != p["id"] and cob["desde"] <= h < cob["hasta"]
                   for cob in coberturas)
    return any(q["flota_id"] == p["flota_id"] and q["id"] != p["id"] and not q["anulada"]
               and q["vigencia_desde"] <= h < q["vigencia_hasta"] for q in pols)


def _calcular(c, hoy: str, extra: int = 0) -> list[dict]:
    """extra: días que se suman a "aparece" de cada tipo (el mail sin alertas mira una semana más: correo.py)."""
    op = opciones._leer(c)
    ritmo = {t: (n + extra, m) for t, (n, m) in ((t, opciones.ritmo(op, t)) for t in opciones.RITMOS)}
    pols = polizas._listar(c)
    coberturas = polizas._coberturas(c)
    alertas = []
    for p in pols:
        alertas.append(alerta_vigencia(p, hoy, *ritmo["vigencia"], sucedida=_sucedida(p, coberturas, pols)))
        if op["avisar_cuotas"]:   # apagado por defecto (opciones.py)
            alertas.append(alerta_cuota(p, hoy, *ritmo["cuota"]))
    for d in documentacion._listar(c, "d.activo = 1 AND coalesce(v.activo, cl.activo) = 1 AND NOT EXISTS "
                                      "(SELECT 1 FROM documentos r WHERE r.renueva_a_id = d.id)", hoy=hoy):
        alertas.append(alerta_documento(d, hoy, *ritmo["documentacion"]))
    # pólizas vencidas cuya alerta de vigencia todavía se ve: id -> día en que terminaron
    terminadas = {a["poliza_id"]: a["fecha"] for a in alertas if a and a["tipo"] == "vigencia" and a["nivel"] == "vencida"}
    for v in c.execute("SELECT v.id, v.dominio, t.cliente_id, cl.apellido_nombre AS cliente FROM vehiculos v "
                       "LEFT JOIN vehiculo_titulares t ON t.vehiculo_id = v.id AND t.hasta IS NULL "
                       "LEFT JOIN clientes cl ON cl.id = t.cliente_id WHERE v.activo = 1").fetchall():
        suyas = [cob for cob in coberturas if cob["vehiculo_id"] == v["id"]]
        if any(cob["desde"] <= hoy < cob["hasta"] for cob in suyas):
            continue
        pasadas = [cob for cob in suyas if cob["hasta"] <= hoy]
        ultima = max(pasadas, key=lambda cob: cob["hasta"], default=None)
        if ultima and terminadas.get(ultima["poliza_id"]) == ultima["hasta"]:
            continue   # una sola alerta: ya está la de vigencia vencida de esa póliza
        proxima = min((cob["desde"] for cob in suyas if cob["desde"] > hoy), default=None)
        alertas.append(alerta_sin_seguro(dict(v), hoy, ultima["hasta"] if ultima else None, proxima))
    return ordenar([a for a in alertas if a])


def listar(*, tipo: str = "", nivel: str = "", hoy: str | None = None, extra: int = 0) -> list[dict]:
    if tipo:
        _opcion(tipo, list(TIPOS), "el tipo de alerta")
    if nivel:
        _opcion(nivel, list(NIVELES), "el nivel")
    with transaccion() as c:
        alertas = _calcular(c, hoy or _hoy(), extra)
    return [a for a in alertas if (not tipo or a["tipo"] == tipo) and (not nivel or a["nivel"] == nivel)]
