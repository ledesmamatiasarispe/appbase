"""Cifrado reversible de los secretos que la app tiene que poder volver a leer (hoy: la contraseña SMTP).

Las contraseñas de los usuarios van con hash (auth.py) porque solo hay que compararlas; la del mail hay que
mandársela al servidor SMTP, así que se CIFRA (Fernet de `cryptography`: AES-128-CBC + HMAC-SHA256, con
autenticación: un texto alterado no se descifra a medias, falla).

LA CLAVE vive en un archivo aparte, data/clave_secretos.key (al lado de la base, fuera del repo como todo data/), y
NO en la base: copiar o mandar solo el .db no expone la contraseña. Se genera sola la primera vez que hace falta
cifrar. Si se pierde (o se copia la base a otra máquina sin el archivo), lo guardado ya no se puede descifrar: la
app no falla, avisa "volvé a cargar la contraseña del mail" (ErrorDeNegocio) y, al cargarla de nuevo, se cifra con
la clave nueva. Para una copia de seguridad completa: el .db Y este archivo.

Formato guardado: "fernet:" + token. Lo que no empieza así es texto plano de una versión anterior: opciones.py lo
cifra al arrancar (migración idempotente) y, mientras tanto, se lee tal cual.
"""
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

from . import db
from .servicios import ErrorDeNegocio

PREFIJO = "fernet:"
ARCHIVO_CLAVE = "clave_secretos.key"
log = logging.getLogger(__name__)


def ruta_clave():
    """Al lado de la base (respeta AUTO_DB y la base temporal de los tests)."""
    return db.DB_PATH.parent / ARCHIVO_CLAVE


def _leer_clave() -> Fernet | None:
    """La clave guardada, o None si no hay archivo o está dañado."""
    try:
        return Fernet(ruta_clave().read_bytes().strip())
    except (OSError, ValueError):
        return None


def _clave_para_cifrar() -> Fernet:
    """La clave existente o una nueva. Dos hilos que la crean a la vez: gana el primero ("xb" no pisa) y el otro
    usa esa. Un archivo dañado se reemplaza: lo cifrado con él ya era ilegible."""
    f = _leer_clave()
    if f:
        return f
    ruta = ruta_clave()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    nueva = Fernet.generate_key()
    try:
        with open(ruta, "xb") as a:
            a.write(nueva)
    except FileExistsError:
        f = _leer_clave()
        if f:
            return f
        log.warning("La clave de cifrado %s estaba dañada: se genera una nueva.", ruta)
        tmp = ruta.with_suffix(".tmp")
        tmp.write_bytes(nueva)
        os.replace(tmp, ruta)
    return Fernet(nueva)


def esta_cifrado(valor: str) -> bool:
    return str(valor or "").startswith(PREFIJO)


def cifrar(texto: str) -> str:
    """'' queda '' (no hay nada que proteger)."""
    if not texto:
        return ""
    return PREFIJO + _clave_para_cifrar().encrypt(texto.encode("utf-8")).decode("ascii")


MENSAJE_ILEGIBLE = ("No se pudo leer la contraseña del mail guardada (falta o cambió la clave de cifrado {archivo} "
                    "en la carpeta data). Volvé a cargar la contraseña del mail en Opciones.")


def descifrar(valor: str) -> str:
    """El texto original. Lanza ErrorDeNegocio con un mensaje claro si la clave falta, está dañada o no es la
    que cifró: nunca un error interno."""
    if not esta_cifrado(valor):
        return str(valor or "")   # vacío, o texto plano de antes de la migración
    f = _leer_clave()
    if f is None:
        raise ErrorDeNegocio(MENSAJE_ILEGIBLE.format(archivo=ARCHIVO_CLAVE))
    try:
        return f.decrypt(valor[len(PREFIJO):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        raise ErrorDeNegocio(MENSAJE_ILEGIBLE.format(archivo=ARCHIVO_CLAVE))


def error_de_lectura(valor: str) -> str:
    """'' si se puede descifrar (o no hay nada); si no, el mensaje para mostrar."""
    try:
        descifrar(valor)
        return ""
    except ErrorDeNegocio as e:
        return str(e)
