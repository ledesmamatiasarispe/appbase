"""Identidad de ESTA app. Es lo único que cambia de una app a otra en la configuración del núcleo.

VERSION se sube a mano antes de publicar, y el tag del release de GitHub tiene que ser "v" + VERSION
(herramientas/compilar.py lo controla). REPO es "usuario/repositorio" en GitHub ("" = no busca actualizaciones);
<PREFIJO>_REPO lo reemplaza (vacío en los tests)."""
VERSION = "0.1.0"
APP = "AppBase"                 # identificador fijo: nombre del .exe, User-Agent, /api/version. No cambia nunca.
NOMBRE = "App base"             # el nombre de fábrica que se ve (se cambia en Opciones)
SUBTITULO = "Ejemplo de app sobre el núcleo"
PREFIJO = "BASE"                # variables de entorno: BASE_DB, BASE_PUERTO, BASE_REPO, BASE_NAVEGADOR
PUERTO = 8090
REPO = ""
LOGIN = "Usuario"
