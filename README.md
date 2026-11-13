# App base

Las herramientas y mejoras comunes de las apps hechas sobre la misma base (FastAPI + SQLite + JavaScript sin
framework, una ventana .exe en Windows que se actualiza sola desde GitHub):

| App | Repositorio | Pantalla de ajustes |
|---|---|---|
| UltraMantenimiento (Fundición Romero) | `super-duper-lamp` | Opciones |
| Gestión Automotor APB | `gestionautomotorapb` | Opciones |
| Edificios de Mamá (consorcios) | `edificiosDeMama` | Administración |

La idea: una mejora de la base se hace una vez, se guarda acá, y se lleva a todas las apps copiando archivos.
Lo propio de cada negocio (mantenimiento, pólizas, expensas) **no** va acá.

## Qué tiene

| Archivo | Qué hace |
|---|---|
| `base/app/marca.py` | Nombre y logo de la app, editables desde la pantalla de ajustes (barra, ingreso y pestaña del navegador). El logo se valida por su contenido, no solo por la extensión. |
| `base/app/puerto.py` | Puerto editable desde la pantalla de ajustes. Al arrancar: si el puerto lo usa otro programa, toma el siguiente libre; si la app ya estaba abierta, solo abre el navegador. |
| `base/app/rutas_base.py` | La página (con `?v=VERSION` para que después de actualizar no haga falta Ctrl+F5, y con el nombre y logo elegidos), `/api/version`, `/api/marca*` y `/api/puerto`. |
| `base/app/actualizador.py` | Actualización desde los releases de GitHub (solo Windows, versión compilada): controla el SHA-256, funciona con antivirus o proxy que revisan HTTPS (certificados del sistema + certifi), copia la base antes de instalar (quedan las últimas 3) y, si la copia del programa falla, vuelve a poner el anterior. |
| `base/frontend/comun.js` + `comun.css` | Banner amarillo de contraseña provisoria (no bloquea la app), cambio de contraseña y las tarjetas Contraseña, Puerto y Nombre y logo. |
| `base/tests/test_base.py` | Los tests de todo lo anterior. |

## Qué pone cada app

En `app/version.py`:

```python
VERSION = "1.0.0"
REPO = os.environ.get("<PREFIJO>_REPO", "usuario/repositorio")
APP = "MiApp"            # identificador fijo (User-Agent, /api/version, nombre del .exe). No es el que se cambia en ajustes.
NOMBRE = "Mi App"        # nombre de fábrica que muestra la página
PREFIJO = "MIAPP"        # de las variables de entorno: MIAPP_DB, MIAPP_PUERTO, MIAPP_REPO...
PUERTO = 8095            # el de fábrica
COMPILADA = bool(getattr(sys, "frozen", False))
```

Además:

- `app/db.py` con `DB_PATH`, `conectar()`, `transaccion()` y una tabla `config (clave TEXT PRIMARY KEY, valor TEXT)`.
- `app/auth.py` con `usuario_actual` y `solo_admin` (dependencias de FastAPI); `usuario_actual` **no** bloquea una
  contraseña provisoria (`debe_cambiar`): el aviso lo pone `comun.js`.
- `ErrorDeNegocio` y `NoEncontrado` en `app/servicios.py` (o en `app/validar.py`).
- En `main.py`: `app.include_router(rutas_base.router)` y `"/"` servido con `rutas_base.pagina(FRONTEND / "index.html")`.
- En `__main__.py`: `puerto, ya_abierta = puerto.al_arrancar()` (ver cualquiera de las tres apps).
- En `index.html`: `comun.css` y `comun.js` (después de `app.js`); la marca con `/static/icono.svg` y/o `/static/logo.svg`.
- En `app.js`: `S`, `$`, `esc`, `api`, `avisar`, `abrirModal`, `cerrarModal`, `irA`, y
  `const PANTALLA_AJUSTES = { vista: 'opciones', titulo: 'Opciones' };`. `entrar()` llama a `bannerPassword()`,
  `salir()` a `quitarBannerPassword()`, y la pantalla de ajustes pone `${await tarjetasBase()}` y después
  `activarTarjetasBase()`.
- En los tests: la fixture `api` (en `tests/test_api.py`) o `cliente` (en `conftest.py`) con el administrador logueado.

## Lo que es igual en lógica pero vive en el `db.py` de cada app

`transaccion()` con `BEGIN IMMEDIATE` + `busy_timeout` (varios usuarios escriben de a uno, sin "database is locked") y
reentrante con `SAVEPOINT`. `executescript` va fuera de la transacción porque confirma solo. Está igual en las tres;
pasarlo a un archivo común está pendiente.

## Cómo se usa

```
python herramientas/sincronizar.py <carpeta de la app>            # qué difiere (no toca nada)
python herramientas/sincronizar.py <carpeta de la app> --llevar   # base -> app: la app recibe las mejoras
python herramientas/sincronizar.py <carpeta de la app> --traer    # app -> base: una mejora hecha en una app
```

1. Una mejora de la base se hace en una app (con sus tests), se trae acá con `--traer` y se anota en `NOVEDADES.md`.
2. Se lleva a las otras con `--llevar` y se corren sus tests (`tests/test_base.py` incluido).
3. Cada app publica su versión como siempre.

`apps.json` lista las apps y qué archivos no toma cada una (Edificios de Mamá tiene su propio actualizador porque
también se instala desde el código fuente y en Linux/Mac; tiene las mismas mejoras).

## Pendiente

- Importar los datos de otra instalación (hoy solo en Gestión Automotor).
- Ayuda por pantalla y Tour (UltraMantenimiento y Gestión Automotor) para Edificios de Mamá, y el chequeo de pasos
  huérfanos de la Ayuda en las tres.
- Historial de cambios y mail semanal (hoy solo en Gestión Automotor).
- `transaccion()` en un archivo común.
