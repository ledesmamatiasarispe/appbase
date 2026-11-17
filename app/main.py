"""La app de ejemplo: el núcleo + los módulos que esta app usa. Una app real es esto mismo con sus propios módulos
(y una fusión de dos apps, la lista de módulos de las dos)."""
from pathlib import Path

import nucleo

from . import version as v

nucleo.configurar(app=v.APP, nombre=v.NOMBRE, prefijo=v.PREFIJO, puerto=v.PUERTO, version=v.VERSION, repo=v.REPO,
                  subtitulo=v.SUBTITULO, login=v.LOGIN, raiz=Path(__file__).resolve().parent.parent)

from modulos import asistente, notas  # noqa: E402  (después de configurar)
from nucleo.aplicacion import crear_app  # noqa: E402

MODULOS = [notas.MODULO, asistente.MODULO]
app = crear_app(MODULOS)
