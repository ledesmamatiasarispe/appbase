"""Importa la planilla de cartera ("LA SEGUNDA ATM.xlsx") a una base de la app: clientes, vehículos, flotas, pólizas
y las cuotas ya vencidas de los planes en curso.

    .venv\\Scripts\\python.exe herramientas\\importar_excel.py <archivo.xlsx> --db <base.db>            (simulación)
    .venv\\Scripts\\python.exe herramientas\\importar_excel.py <archivo.xlsx> --db <base.db> --aplicar  (escribe)

SIMULACIÓN (sin --aplicar): no escribe NADA en la base indicada. Hace exactamente lo mismo que --aplicar sobre una
copia temporal (API de backup de sqlite, una foto consistente aunque la app esté usándola), imprime el reporte y borra
la copia. Así el reporte sale de las MISMAS reglas que se van a aplicar (superposición, dominios, mails...), no de
una imitación. Si la base no existe, se simula sobre una base nueva vacía.

--aplicar: antes de escribir, copia la base al lado (<base>_antes_de_importar_<fecha-hora>.db), como pide el
CLAUDEREADME para toda migración de una base real. Si la base no existe, la crea (con el administrador inicial).

UNA TRANSACCIÓN POR FILA (no por archivo): una fila es una póliza con su cliente, vehículo/flota y pagos, y entra
entera o no entra (si la póliza choca, no queda un cliente o un vehículo suelto). Una fila mala no frena a las
demás: se reporta y, como la herramienta es idempotente, se corrige el Excel y se vuelve a correr. Además no retiene
el permiso de escritura de la base durante todo el archivo si otros usuarios la están usando.

SOLO SERVICIOS: todo pasa por clientes/vehiculos/flotas/polizas (las mismas reglas, auditoría e historial que la
pantalla), nunca SQL directo. Los varios casos de uso de una fila se componen en una transacción porque
db.transaccion() es reentrante. El usuario de la auditoría es "Importación" (sin legajo: no es una cuenta que pueda
entrar a la app), para distinguir en el historial lo que vino del Excel de lo cargado a mano.

IDEMPOTENTE: cliente por nombre normalizado (sin acentos, mayúsculas ni signos), vehículo por dominio, flota por
nombre dentro del cliente, póliza por compañía + número. Una póliza que ya existe no se toca (ni sus pagos).

CUOTAS A MITAD DE PLAN: sin los pagos ya hechos, cada póliza en curso aparecería con cuotas vencidas desde el primer
día. Ver planificar_cuotas(): se arma el calendario de vencimientos y se registran como pagadas (fecha de pago = su
vencimiento, con una nota) las anteriores al próximo vencimiento conocido. Lo que no se puede deducir queda sin
pagos y en "REVISAR".
"""
import argparse
import re
import shutil
import sqlite3
import sys
import tempfile
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from app import clientes, companias, db, flotas, polizas, vehiculos  # noqa: E402
from app.servicios import ErrorDeNegocio, NoEncontrado, _fecha, _hoy  # noqa: E402

USUARIO = {"legajo": None, "nombre": "Importación"}
NOTA_PAGO = "Registrada por la importación del Excel: se supone pagada porque es anterior al próximo vencimiento " \
            "({motivo}). Fecha de pago = su vencimiento."

# campo -> encabezados posibles, ya normalizados con _clave() (sin acentos ni espacios: "A�O" queda "AO")
COLUMNAS = {
    "asegurado": ("ASEGURADO",),
    "poliza": ("POLIZA",),
    "dominio": ("DOMINIO", "DOMINIIO"),
    "marca_modelo": ("MARCAYMODELO",),
    "marca": ("MARCA",),
    "modelo": ("MODELO",),
    "tipo": ("TIPO",),
    "anio": ("ANO", "AO", "ANIO"),
    "uso": ("USO",),
    "zona": ("ZONARIESGO", "ZONADERIESGO"),
    "cobertura": ("COBERTURA",),
    "desde": ("VIGENCIADESDE",),
    "hasta": ("VIGENCIAHASTA",),
    "medio_pago": ("MEDIODEPAGO",),
    "plan": ("PLANDEPAGOS",),
    "mail": ("MAIL",),
    "fecha_refacturacion": ("FECHAREFACTURACION",),
    "refacturacion": ("REFACTURACION",),
}
OBLIGATORIAS = ("asegurado", "poliza", "dominio", "desde", "hasta")
FILAS_BUSCAR_ENCABEZADO = 10


# ── lectura del Excel ───────────────────────────────────────────────────────

def _sin_acentos(texto: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(ch))


def _clave(valor) -> str:
    """Encabezado comparable: mayúsculas, sin acentos y solo letras y dígitos ('DOMINIIO ' -> 'DOMINIIO',
    'A�O' -> 'AO', 'Año' -> 'ANO')."""
    return re.sub(r"[^A-Z0-9]", "", _sin_acentos(str(valor or "")).upper())


def clave_nombre(valor) -> str:
    """Nombre de cliente comparable: 'Pérez, José' y 'PEREZ JOSE' son el mismo."""
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", _sin_acentos(str(valor or "")).upper()).split())


def _txt(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return " ".join(str(valor).split())


def fecha_excel(valor, campo: str) -> str | None:
    """Fecha de una celda: datetime/date (lo normal), texto ISO o dd/mm/aaaa, o número de serie de Excel."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, (int, float)) and 20000 < valor < 80000:
        return (date(1899, 12, 30) + timedelta(days=int(valor))).isoformat()
    t = str(valor).strip()
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", t)
    if m:
        try:
            return date(int(m[3]), int(m[2]), int(m[1])).isoformat()
        except ValueError:
            pass
    return _fecha(t, campo)   # ISO, o el mismo mensaje de error que da la app


def _encabezado(filas: list[tuple]) -> tuple[int, dict[str, int]] | None:
    """La fila de encabezado se busca por nombres de columna (LA SEGUNDA la tiene en la 1, ATM en la 2)."""
    for i, fila in enumerate(filas[:FILAS_BUSCAR_ENCABEZADO]):
        claves = [_clave(v) for v in fila]
        if "ASEGURADO" in claves and "POLIZA" in claves:
            columnas = {}
            for campo, nombres in COLUMNAS.items():
                for j, k in enumerate(claves):
                    if k in nombres and campo not in columnas:
                        columnas[campo] = j
            return i, columnas
    return None


def leer_hojas(archivo: Path) -> list[dict]:
    """[{hoja, filas: [{fila (número en el Excel), datos: {campo: valor}}], error}] de cada hoja del archivo."""
    import openpyxl   # solo la herramienta lo necesita (requirements-dev.txt), no la app
    # sin read_only: así iter_rows trae también los renglones vacíos y el número de fila es el del Excel
    libro = openpyxl.load_workbook(archivo, data_only=True)
    hojas = []
    try:
        for hoja in libro.worksheets:
            filas = list(hoja.iter_rows(values_only=True))
            enc = _encabezado(filas)
            if enc is None:
                hojas.append({"hoja": hoja.title, "filas": [], "error": "no se encontró la fila de encabezado "
                              "(una fila con ASEGURADO y POLIZA en las primeras 10)"})
                continue
            i, columnas = enc
            faltan = [c.upper() for c in OBLIGATORIAS if c not in columnas]
            if faltan:
                hojas.append({"hoja": hoja.title, "filas": [], "error": f"faltan las columnas {', '.join(faltan)}"})
                continue
            datos = []
            for n, fila in enumerate(filas[i + 1:], start=i + 2):
                if all(v is None or (isinstance(v, str) and not v.strip()) for v in fila):
                    continue
                datos.append({"fila": n, "datos": {c: (fila[j] if j < len(fila) else None) for c, j in columnas.items()}})
            hojas.append({"hoja": hoja.title, "filas": datos, "error": None})
    finally:
        libro.close()
    return hojas


# ── cuotas ──────────────────────────────────────────────────────────────────

def _plan(valor) -> int | None:
    """'3 CUOTAS' -> 3. None si viene vacío. ValueError si no se entiende."""
    t = _txt(valor)
    if not t:
        return None
    m = re.fullmatch(r"(\d+)\s*(CUOTAS?)?", t.upper())
    if not m or not 1 <= int(m[1]) <= polizas.MAX_CUOTAS:
        raise ValueError(t)
    return int(m[1])


def _frecuencia(valor) -> str | None:
    t = _sin_acentos(_txt(valor)).lower()
    if not t:
        return None
    if t not in polizas.FRECUENCIAS:
        raise ValueError(_txt(valor))
    return t


def _meses_justos(desde: str, hasta: str) -> int | None:
    a, b = date.fromisoformat(desde), date.fromisoformat(hasta)
    return (b.year - a.year) * 12 + b.month - a.month if a.day == b.day else None


def planificar_cuotas(desde: str, hasta: str, hoy: str, *, plan=None, refacturacion=None, fecha_refacturacion=None) -> dict:
    """Qué cargar en la póliza y qué pagos registrar, a partir de lo que trae la fila.

    - Frecuencia: la columna REFACTURACION; si no hay pero el plan divide justo la vigencia en una frecuencia
      conocida (3 cuotas en 3 meses), se deduce (y se avisa en "deducido").
    - Calendario: vencimientos cada `frecuencia` meses dentro de [desde, hasta) (el mismo criterio que el cronograma),
      anclados en FECHA REFACTURACION si viene (el próximo vencimiento conocido) o en la vigencia desde. Se calculan
      desde el ancla (ancla ± k meses), no encadenados, para no arrastrar el recorte de fin de mes.
    - Cantidad de cuotas: el plan si viene; si no, las del calendario.
    - Pagadas: con FECHA REFACTURACION, las anteriores a ella; sin ella, las que vencieron antes de hoy (vencimiento
      = último día válido: la de hoy todavía no venció y queda como próxima).
    - Lo que no cierra (plan y refacturación que no coinciden, fecha fuera de la vigencia, textos que no se entienden)
      queda sin pagos ni primer vencimiento, con el motivo en "revisar".
    Devuelve {cantidad_cuotas, frecuencia, primer_vencimiento, pagos [(vencimiento, siguiente|None)], proximo,
    revisar [texto], deducido [texto]}."""
    r = {"cantidad_cuotas": 1, "frecuencia": "ninguna", "primer_vencimiento": None, "pagos": [], "proximo": None,
         "revisar": [], "deducido": []}
    try:
        cuotas = _plan(plan)
    except ValueError as e:
        r["revisar"].append(f"plan de pagos '{e}' no se entiende: cargar las cuotas a mano")
        return r
    try:
        frecuencia = _frecuencia(refacturacion)
    except ValueError as e:
        r["revisar"].append(f"refacturación '{e}' no es una frecuencia conocida ({', '.join(polizas.FRECUENCIAS)})")
        if cuotas:
            r["cantidad_cuotas"] = cuotas
        return r
    if cuotas:
        r["cantidad_cuotas"] = cuotas
    if frecuencia is None and cuotas and cuotas > 1:
        meses = _meses_justos(desde, hasta)
        deducida = next((f for f, m in polizas.FRECUENCIAS.items() if m and meses and m * cuotas == meses), None)
        if deducida is None:
            r["revisar"].append(f"{cuotas} cuotas sin refacturación y la vigencia no se divide en una frecuencia "
                                "conocida: cargar los vencimientos a mano")
            return r
        frecuencia = deducida
        r["deducido"].append(f"frecuencia {deducida} deducida ({cuotas} cuotas en {meses} meses de vigencia)")
    if frecuencia is None and not cuotas:
        if fecha_refacturacion:
            r["revisar"].append("hay fecha de refacturación pero no plan de pagos ni frecuencia: cargar las cuotas a mano")
        else:
            r["revisar"].append("sin plan de pagos ni refacturación: se cargó en 1 cuota sin vencimiento")
        return r
    r["frecuencia"] = frecuencia or "ninguna"
    meses = polizas.FRECUENCIAS[r["frecuencia"]]

    ancla = fecha_refacturacion or desde
    if not desde <= ancla < hasta:
        r["revisar"].append(f"la fecha de refacturación {polizas._dmy(ancla)} está fuera de la vigencia: cargar las "
                            "cuotas a mano")
        return r
    if meses:
        atras, k = [], 1
        while (v := polizas._sumar_meses(ancla, -k * meses)) >= desde:
            atras.append(v)
            k += 1
        adelante, k = [], 0
        while (v := polizas._sumar_meses(ancla, k * meses)) < hasta:
            adelante.append(v)
            k += 1
        calendario = list(reversed(atras)) + adelante
    else:
        calendario = [ancla]   # cuota única
    if cuotas and len(calendario) != cuotas:
        r["revisar"].append(f"el plan dice {cuotas} cuotas pero la refacturación {r['frecuencia']} da {len(calendario)} "
                            "en la vigencia: cargar los vencimientos a mano")
        return r
    r["cantidad_cuotas"] = len(calendario)
    if not cuotas:
        r["deducido"].append(f"{len(calendario)} cuota(s) deducidas: refacturación {r['frecuencia']} dentro de la vigencia")
    if fecha_refacturacion and meses:
        r["deducido"].append(f"vencimientos anclados en la fecha de refacturación del Excel "
                             f"({polizas._dmy(fecha_refacturacion)}), cada {meses} mes(es)")
    r["primer_vencimiento"] = calendario[0]
    tope = fecha_refacturacion or hoy
    pagadas = [v for v in calendario if v < tope]
    r["pagos"] = [(v, calendario[i + 1] if i + 1 < len(calendario) else None) for i, v in enumerate(pagadas)]
    r["proximo"] = calendario[len(pagadas)] if len(pagadas) < len(calendario) else None
    if fecha_refacturacion and fecha_refacturacion < hoy:
        r["revisar"].append(f"la fecha de refacturación {polizas._dmy(fecha_refacturacion)} ya pasó: si se pagó, "
                            "registrar el pago")
    return r


# ── importación de una fila ─────────────────────────────────────────────────

class Rechazo(Exception):
    pass


def _buscar_cliente(nombre: str) -> dict | None:
    clave = clave_nombre(nombre)
    iguales = [c for c in clientes.listar(incluir_baja=True) if clave_nombre(c["apellido_nombre"]) == clave]
    if len(iguales) > 1:
        raise Rechazo(f"hay {len(iguales)} clientes que se llaman como '{nombre}' en la base: no se sabe cuál es")
    return iguales[0] if iguales else None


def _buscar_vehiculo(dominio: str) -> dict | None:
    return next((v for v in vehiculos.listar(q=dominio, incluir_baja=True) if v["dominio"] == dominio), None)


def _buscar_poliza(compania_id: int, numero: str) -> dict | None:
    return next((p for p in polizas.listar(q=numero, compania_id=compania_id, incluir_anuladas=True)
                 if p["numero"] == numero), None)


def _marca_modelo(d: dict) -> tuple[str, str]:
    if "marca_modelo" in d and "marca" not in d:
        partes = _txt(d["marca_modelo"]).split(" ", 1)   # "BAJAJ ROUSER 1570": la primera palabra es la marca
        return partes[0], partes[1] if len(partes) > 1 else ""
    return _txt(d.get("marca")), _txt(d.get("modelo"))


def importar_fila(compania: dict, hoja: str, fila: int, d: dict, hoy: str) -> dict:
    """Una fila en UNA transacción (cliente + vehículo/flota + póliza + pagos, o nada)."""
    res = {"hoja": hoja, "fila": fila, "asegurado": _txt(d.get("asegurado")), "dominio": _txt(d.get("dominio")),
           "poliza": _txt(d.get("poliza")), "estado": None, "acciones": [], "revisar": [], "motivo": ""}
    try:
        with db.transaccion():
            _importar(compania, hoja, fila, d, hoy, res)
    except (Rechazo, ErrorDeNegocio, NoEncontrado) as e:
        res.update(estado="rechazada", motivo=str(e), acciones=[], revisar=[])
    return res


def _importar(compania: dict, hoja: str, fila: int, d: dict, hoy: str, res: dict) -> None:
    asegurado = _txt(d.get("asegurado"))
    if not asegurado:
        raise Rechazo("falta el asegurado")
    numero = polizas.normalizar_numero(d.get("poliza"))
    res["poliza"] = numero
    desde = fecha_excel(d.get("desde"), "la vigencia desde")
    hasta = fecha_excel(d.get("hasta"), "la vigencia hasta")
    if not desde or not hasta:
        raise Rechazo("falta la vigencia desde o hasta")
    existente = _buscar_poliza(compania["id"], numero)
    if existente:
        res["estado"] = "existente"
        res["acciones"].append(f"la póliza {numero} de {compania['nombre']} ya está cargada (id {existente['id']}): "
                               "no se toca")
        return

    # cliente
    cl = _buscar_cliente(asegurado)
    mail = _txt(d.get("mail"))
    if cl:
        res["acciones"].append(f"cliente existente: {cl['apellido_nombre']} (id {cl['id']})")
        if mail and mail.lower() != (cl["mail"] or ""):
            res["revisar"].append(f"el Excel dice mail {mail} y el cliente tiene '{cl['mail']}': no se cambió")
    else:
        cl = clientes.crear(USUARIO, apellido_nombre=asegurado, mail=mail)
        res["acciones"].append(f"cliente nuevo: {asegurado}" + (f" ({cl['mail']})" if mail else ""))

    # lo que cubre: un vehículo o, con DOMINIO = FLOTA, una flota del cliente
    cubre = {}
    if vehiculos.limpiar_dominio(d.get("dominio")) == "FLOTA":
        nombre = f"Flota póliza {numero}"
        fl = next((f for f in flotas.listar(cliente_id=cl["id"], incluir_baja=True)
                   if clave_nombre(f["nombre"]) == clave_nombre(nombre)), None)
        if fl:
            res["acciones"].append(f"flota existente: '{fl['nombre']}'")
        else:
            datos = ", ".join(f"{k} {_txt(d.get(k))}" for k in ("tipo", "uso") if _txt(d.get(k)))
            fl = flotas.crear(USUARIO, nombre=nombre, cliente_id=cl["id"],
                              notas=f"Importada del Excel (hoja {hoja}, fila {fila}) sin vehículos: cargarlos desde la "
                                    f"flota." + (f" El Excel decía: {datos}." if datos else ""))
            res["acciones"].append(f"flota nueva sin vehículos: '{nombre}' (cargarle los vehículos)")
        cubre["flota_id"] = fl["id"]
        res["dominio"] = "FLOTA"
    else:
        dominio = vehiculos.normalizar_dominio(d.get("dominio"))
        res["dominio"] = dominio
        v = _buscar_vehiculo(dominio)
        if v:
            if v["cliente_id"] != cl["id"]:
                raise Rechazo(f"el dominio {dominio} ya está cargado como de {v['cliente'] or 'nadie'}, no de "
                              f"{asegurado}: revisar a mano (venta o error de carga)")
            res["acciones"].append(f"vehículo existente: {dominio}")
        else:
            marca, modelo = _marca_modelo(d)
            v = vehiculos.crear(USUARIO, cliente_id=cl["id"], desde=min(desde, hoy), dominio=dominio, marca=marca,
                                modelo=modelo, tipo=_txt(d.get("tipo")), anio=d.get("anio"), uso=_txt(d.get("uso")))
            res["acciones"].append(f"vehículo nuevo: {dominio} {marca} {modelo}".rstrip())
        cubre["vehiculo_id"] = v["id"]

    # póliza y cuotas
    try:
        fecha_ref = fecha_excel(d.get("fecha_refacturacion"), "la fecha de refacturación")
    except ErrorDeNegocio:
        fecha_ref = None
        res["revisar"].append(f"fecha de refacturación '{_txt(d.get('fecha_refacturacion'))}' no es una fecha: se ignoró")
    plan = planificar_cuotas(desde, hasta, hoy, plan=d.get("plan"), refacturacion=d.get("refacturacion"),
                             fecha_refacturacion=fecha_ref)
    res["revisar"] += plan["revisar"]
    notas = f"Importada del Excel (hoja {hoja}, fila {fila})."
    if plan["revisar"]:
        notas += " Revisar las cuotas: " + "; ".join(plan["revisar"]) + "."
    p = polizas.crear(USUARIO, compania_id=compania["id"], numero=numero, cliente_id=cl["id"], **cubre,
                      cobertura=_txt(d.get("cobertura")), zona_riesgo=_txt(d.get("zona")), vigencia_desde=desde,
                      vigencia_hasta=hasta, medio_pago=_txt(d.get("medio_pago")), cantidad_cuotas=plan["cantidad_cuotas"],
                      frecuencia_refacturacion=plan["frecuencia"], primer_vencimiento=plan["primer_vencimiento"],
                      notas=notas)
    motivo = "fecha de refacturación del Excel" if fecha_ref else "su vencimiento ya pasó"
    for vencimiento, siguiente in plan["pagos"]:
        p = polizas.registrar_pago(USUARIO, p["id"], fecha_pago=vencimiento, nuevo_vencimiento=siguiente,
                                   notas=NOTA_PAGO.format(motivo=motivo))
    texto = (f"póliza nueva: {numero} de {compania['nombre']} del {polizas._dmy(desde)} al {polizas._dmy(hasta)}, "
             f"{plan['cantidad_cuotas']} cuota(s), refacturación {plan['frecuencia']}")
    res["acciones"].append(texto)
    for x in plan["deducido"]:
        res["acciones"].append(x)
    if plan["pagos"]:
        res["acciones"].append(f"{len(plan['pagos'])} cuota(s) registradas como pagadas por la importación "
                               f"({', '.join(polizas._dmy(v) for v, _ in plan['pagos'])}); "
                               + (f"queda {p['cuota_texto']}, vence el {polizas._dmy(p['vencimiento_cuota'])}"
                                  if p["proxima_cuota"] else f"plan completo ({p['cuota_texto']})"))
    elif plan["primer_vencimiento"]:
        res["acciones"].append(f"sin cuotas vencidas: próxima {p['cuota_texto']}, vence el "
                               f"{polizas._dmy(p['vencimiento_cuota'])}")
    res["estado"] = "importada"


# ── todo el archivo ─────────────────────────────────────────────────────────

def _copiar_base(origen: Path, destino: Path) -> None:
    """Foto consistente de la base (aunque la app la esté usando): API de backup de sqlite."""
    a, b = sqlite3.connect(origen), sqlite3.connect(destino)
    try:
        a.backup(b)
    finally:
        a.close()
        b.close()


def importar(archivo, base, *, aplicar: bool = False, hoy: str | None = None) -> dict:
    """Corre la importación y devuelve el reporte (ver imprimir()). Sin aplicar, sobre una copia temporal."""
    archivo, base = Path(archivo), Path(base)
    hoy = hoy or _hoy()
    hojas = leer_hojas(archivo)
    reporte = {"archivo": str(archivo), "base": str(base), "aplicar": aplicar, "hoy": hoy, "respaldo": None,
               "base_nueva": not base.exists(), "hojas": [], "filas": []}
    temporal = None
    anterior = db.DB_PATH
    try:
        if aplicar:
            if base.exists():
                respaldo = base.with_name(f"{base.stem}_antes_de_importar_{datetime.now():%Y%m%d_%H%M%S}.db")
                _copiar_base(base, respaldo)
                reporte["respaldo"] = str(respaldo)
            db.DB_PATH = base
        else:
            temporal = Path(tempfile.mkdtemp(prefix="importar_simulacion_"))
            if base.exists():
                _copiar_base(base, temporal / "simulacion.db")
            db.DB_PATH = temporal / "simulacion.db"
        db.inicializar()
        por_nombre = {clave_nombre(c["nombre"]): c for c in companias.listar(incluir_baja=True)}
        for h in hojas:
            compania = por_nombre.get(clave_nombre(h["hoja"]))
            error = h["error"] or (None if compania else f"no hay una compañía llamada '{h['hoja']}' en la base")
            reporte["hojas"].append({"hoja": h["hoja"], "filas": len(h["filas"]), "error": error,
                                     "compania": compania["nombre"] if compania else None})
            if error:
                continue
            for f in h["filas"]:
                reporte["filas"].append(importar_fila(compania, h["hoja"], f["fila"], f["datos"], hoy))
    finally:
        db.DB_PATH = anterior
        if temporal:
            shutil.rmtree(temporal, ignore_errors=True)
    return reporte


def imprimir(rep: dict, salida=None) -> None:
    salida = salida or sys.stdout
    p = lambda *a: print(*a, file=salida)   # noqa: E731
    modo = "APLICADO" if rep["aplicar"] else "SIMULACIÓN (no se escribió nada en la base)"
    p(f"Importación de {rep['archivo']}")
    p(f"Base: {rep['base']}{' (nueva)' if rep['base_nueva'] else ''}  -  {modo}  -  hoy: {polizas._dmy(rep['hoy'])}")
    if rep["respaldo"]:
        p(f"Copia de la base antes de importar: {rep['respaldo']}")
    for h in rep["hojas"]:
        p(f"  Hoja '{h['hoja']}': {h['filas']} filas" + (f" -> {h['compania']}" if h["compania"] else "")
          + (f"  ** NO SE IMPORTA: {h['error']}" if h["error"] else ""))
    cuenta = {e: sum(1 for f in rep["filas"] if f["estado"] == e) for e in ("importada", "existente", "rechazada")}
    verbo = "importadas" if rep["aplicar"] else "se importarían"
    p(f"Filas: {cuenta['importada']} {verbo}, {cuenta['existente']} ya estaban, {cuenta['rechazada']} rechazadas, "
      f"{sum(1 for f in rep['filas'] if f['revisar'])} para revisar.")
    for titulo, estado in (("NUEVAS" if rep["aplicar"] else "SE CREARÍA", "importada"), ("YA EXISTEN", "existente"),
                           ("RECHAZADAS", "rechazada")):
        filas = [f for f in rep["filas"] if f["estado"] == estado]
        if not filas:
            continue
        p("")
        p(f"== {titulo} ==")
        for f in filas:
            p(f"[{f['hoja']} fila {f['fila']}] {f['asegurado']} - {f['dominio']} - póliza {f['poliza']}")
            for a in f["acciones"]:
                p(f"    {a}")
            if f["motivo"]:
                p(f"    MOTIVO: {f['motivo']}")
    revisar = [f for f in rep["filas"] if f["revisar"]]
    if revisar:
        p("")
        p("== REVISAR ==")
        for f in revisar:
            p(f"[{f['hoja']} fila {f['fila']}] {f['asegurado']} - póliza {f['poliza']}")
            for r in f["revisar"]:
                p(f"    {r}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Importa el Excel de cartera (hojas por compañía) a una base de la app.")
    ap.add_argument("archivo", help="el .xlsx")
    ap.add_argument("--db", required=True, help="la base .db de destino (se crea si no existe, solo con --aplicar)")
    ap.add_argument("--aplicar", action="store_true", help="escribir de verdad (sin esto, solo simula)")
    args = ap.parse_args(argv)
    if not Path(args.archivo).is_file():
        print(f"No existe el archivo {args.archivo}", file=sys.stderr)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")   # la consola de Windows no tiene todos los caracteres
    rep = importar(args.archivo, args.db, aplicar=args.aplicar)
    imprimir(rep)
    return 1 if any(f["estado"] == "rechazada" for f in rep["filas"]) or any(h["error"] for h in rep["hojas"]) else 0


if __name__ == "__main__":
    sys.exit(main())
