"""Traer los datos de otra instalación: una versión vieja en otra carpeta (la que quedó al bajar el .zip a mano) o la
carpeta data copiada de otra PC.

REEMPLAZA, no fusiona: la base de acá pasa a ser la de la otra instalación, con sus adjuntos (pólizas originales,
fotos) y su clave de secretos (sin ella la contraseña del mail no se podría leer). Fusionar dos bases con datos
propios cada una es otro problema (ids que chocan, el mismo cliente cargado dos veces) y no se hace acá.

Antes de tocar nada:
  - se valida que la otra base sea de esta app (tablas propias e integrity_check) y que no sea la misma de acá;
  - se RESPALDA lo de acá en data/respaldo_antes_de_importar_<fecha_hora>/ (base, adjuntos y clave).
La base se copia con la API de backup de SQLite (respeta los bloqueos de las otras conexiones de la app, no hace falta
cerrarla) desde la otra abierta en solo lectura: la de origen no se toca. Después corre db.inicializar(), que lleva la
base vieja al esquema de esta versión (las mismas migraciones que al arrancar).

Después de importar valen los USUARIOS de la base importada: las sesiones de acá se pierden y hay que volver a entrar.
"""
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from . import db, secretos
from .servicios import ErrorDeNegocio, _registrar

NOMBRE_BASE = "automotor.db"
_TABLAS = ("usuarios", "clientes", "vehiculos", "companias", "polizas", "historial", "config")
_CONTAR = (("clientes", "clientes"), ("vehículos", "vehiculos"), ("flotas", "flotas"), ("pólizas", "polizas"),
           ("documentos", "documentos"), ("usuarios", "usuarios"))


def _buscar_base(ruta) -> Path:
    """Acepta la carpeta de la instalación, su carpeta data o el archivo de la base."""
    texto = str(ruta or "").strip().strip('"')
    if not texto:
        raise ErrorDeNegocio("Falta la carpeta de la otra instalación.")
    p = Path(texto)
    for candidato in (p, p / NOMBRE_BASE, p / "data" / NOMBRE_BASE):
        if candidato.is_file():
            return candidato.resolve()
    raise ErrorDeNegocio(f"No se encontró {NOMBRE_BASE} en '{texto}' (ni en su carpeta data). Tiene que ser una ruta "
                         "de la PC donde corre la app (la PC servidor).")


def _abrir_solo_lectura(base: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{base.as_uri()}?mode=ro", uri=True)
    try:
        tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ErrorDeNegocio(f"La base {base} está dañada: no se importa.")
    except sqlite3.DatabaseError as e:
        conn.close()
        raise ErrorDeNegocio(f"{base} no es una base de datos de la app ({e}).") from e
    except ErrorDeNegocio:
        conn.close()
        raise
    faltan = [t for t in _TABLAS if t not in tablas]
    if faltan:
        conn.close()
        raise ErrorDeNegocio(f"{base} no es una base de esta app (le faltan las tablas {', '.join(faltan)}).")
    return conn


def _conteos(conn: sqlite3.Connection) -> dict:
    tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {nombre: conn.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0] if tabla in tablas else 0
            for nombre, tabla in _CONTAR}


def _archivos(carpeta: Path) -> int:
    return sum(1 for x in carpeta.rglob("*") if x.is_file()) if carpeta.is_dir() else 0


def _exigir_otra(origen: Path) -> None:
    if origen == db.DB_PATH.resolve():
        raise ErrorDeNegocio("Esa es la base que la app ya está usando: elegí la carpeta de la OTRA instalación.")


def revisar(ruta) -> dict:
    """Qué se traería y qué hay acá ahora, sin tocar nada (para mostrar antes de confirmar)."""
    origen = _buscar_base(ruta)
    _exigir_otra(origen)
    conn = _abrir_solo_lectura(origen)
    try:
        importar = _conteos(conn)
    finally:
        conn.close()
    actual = db.conectar()
    try:
        aca = _conteos(actual)
    finally:
        actual.close()
    return {"ruta_base": str(origen), "importar": importar, "actual": aca,
            "adjuntos": _archivos(origen.parent / "adjuntos"), "clave": (origen.parent / secretos.ARCHIVO_CLAVE).is_file()}


def _respaldar(destino: Path) -> None:
    destino.mkdir(parents=True)
    aca = db.conectar()
    copia = sqlite3.connect(destino / NOMBRE_BASE)
    try:
        aca.backup(copia)
    finally:
        copia.close()
        aca.close()
    datos = db.DB_PATH.parent
    if (datos / "adjuntos").is_dir():
        shutil.copytree(datos / "adjuntos", destino / "adjuntos")
    if secretos.ruta_clave().is_file():
        shutil.copy2(secretos.ruta_clave(), destino / secretos.ARCHIVO_CLAVE)


def aplicar(usuario: dict, ruta) -> dict:
    origen = _buscar_base(ruta)
    _exigir_otra(origen)
    conn = _abrir_solo_lectura(origen)   # valida ANTES de respaldar o tocar nada
    datos = db.DB_PATH.parent
    respaldo = datos / f"respaldo_antes_de_importar_{datetime.now():%Y%m%d_%H%M%S}"
    try:
        _respaldar(respaldo)
        aca = db.conectar()
        try:
            conn.backup(aca)
        finally:
            aca.close()
    finally:
        conn.close()
    # adjuntos y clave: los de la otra instalación (los de acá quedaron en el respaldo). Si la base elegida es otro
    # archivo de esta misma carpeta data (un respaldo viejo), sus adjuntos y su clave son los de acá: no se tocan.
    if origen.parent != datos.resolve():
        shutil.rmtree(datos / "adjuntos", ignore_errors=True)
        if (origen.parent / "adjuntos").is_dir():
            shutil.copytree(origen.parent / "adjuntos", datos / "adjuntos")
        if (origen.parent / secretos.ARCHIVO_CLAVE).is_file():
            shutil.copy2(origen.parent / secretos.ARCHIVO_CLAVE, secretos.ruta_clave())
    db.inicializar()   # la base vieja pasa al esquema de esta versión
    with db.transaccion() as c:
        conteos = _conteos(c)
        _registrar(c, usuario, "sistema", 1, "importacion_version", None,
                   {"origen": str(origen), "respaldo": str(respaldo), **conteos})
    return {"importados": conteos, "respaldo": str(respaldo)}
