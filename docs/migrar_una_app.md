# Pasar una app existente al núcleo

Receta tomada de **UltraMantenimiento 1.1.0**, la primera app migrada (2026-11-13). Seguirla igual con Gestión
Automotor y Edificios de Mamá. El código de esa migración, para copiar, está en `ejemplos/migracion_ultramantenimiento/`.

## 0. Antes de empezar

- Hacer un commit con lo que haya pendiente: la migración va en un commit propio.
- Copiar la base real (con la API de backup de SQLite, consistente aunque la app esté abierta) a una carpeta de
  prueba. **Nunca** probar contra la base real.
- Anotar los conteos de las tablas principales para compararlos después.

## 1. Traer el núcleo

Desde appbase: `python herramientas/sincronizar.py <carpeta de la app> --llevar`. Deja `nucleo/`, `modulos/__init__.py`
y `tests/test_nucleo_intacto.py`. Copiar también `herramientas/compilar.py` y, si no lo tiene, `pytest.ini`.

## 2. El módulo: todo lo de negocio

Crear `modulos/<nombre>/` y mover ahí (con `git mv`, para conservar la historia):

| Antes | Después |
|---|---|
| `app/servicios.py`, `app/<lógica>.py` | `modulos/<nombre>/servicios.py`, ... |
| las rutas de dominio de `app/main.py` | `modulos/<nombre>/rutas.py` (`APIRouter`, `@router.` en vez de `@app.`) |
| `app/db.py`: tablas de negocio, columnas nuevas, migraciones, ejemplos | `modulos/<nombre>/esquema.py` (`ESQUEMA`, `migrar(c)`, `datos_iniciales(c)`) |
| `frontend/app.js` (solo las pantallas de negocio) | `modulos/<nombre>/frontend/<nombre>.js` |
| los pasos de `frontend/ayuda.js` | `modulos/<nombre>/frontend/ayuda_<nombre>.js` (registrados en `Ayuda.pasos` / `Ayuda.tour`) |
| lo propio de `styles.css` | `modulos/<nombre>/frontend/<nombre>.css` |
| el ícono | `app/frontend/icono.svg` (se pasa con `configurar(frontend=...)`) |

Y en los imports del código movido:
- `from . import db` / `from .db import transaccion` → `from nucleo import db` / `from nucleo.db import transaccion`;
- las clases `ErrorDeNegocio` / `NoEncontrado` propias → `from nucleo.errores import ErrorDeNegocio, NoEncontrado`
  (tienen que ser las del núcleo para que se traduzcan a 400/404);
- `Usuario` / `Admin` de las rutas → `from nucleo.auth import Admin, Usuario`.

`modulos/<nombre>/__init__.py` arma `MODULO = Modulo(...)` con el menú (un `Menu` por pestaña, con `orden`), los scripts
en el orden en que se cargan (pantallas, después la ayuda) y `al_iniciar` para lo que antes corría en el arranque.

## 3. La app

- `app/version.py`: `VERSION` (subirla), `APP` (el nombre del .exe: **no cambiarlo**, el actualizador lo busca),
  `NOMBRE`, `SUBTITULO`, `PREFIJO` (el mismo de antes: `MANT`, `AUTO`, `EDIF`), `PUERTO`, `REPO`, `LOGIN`, `BASE`
  (el nombre del .db de antes, para que siga usando el mismo archivo).
- `app/main.py`: `nucleo.configurar(...)` y `crear_app([modulo.MODULO])`. `app/__main__.py`: `correr(app)`.
- Borrar lo que ahora da el núcleo: `auth.py`, `usuarios.py`, `db.py`, `actualizador.py`, `marca.py`, `puerto.py`,
  `rutas_base.py`, `index.html`, `comun.*`, `ayuda.*`, y del `app.js` todo lo general (utilidades, sesión, navegación,
  Opciones, Usuarios). **Ninguna constante ni función global puede quedar declarada dos veces** (`MESES`, `S`, `$`,
  `api`...): el navegador no carga el archivo y todas las pantallas del módulo desaparecen sin aviso visible.

## 4. Usuarios: la parte delicada

El núcleo usa `usuarios(id, usuario, ...)` y `sesiones(usuario_id, ...)`. Si la app tenía otra forma, `migrar(c)` la
convierte **dentro de la transacción del núcleo** y antes de que nadie use las tablas:

- UltraMantenimiento tenía `usuarios(legajo INTEGER PRIMARY KEY)`: `ALTER TABLE usuarios RENAME COLUMN legajo TO id`
  (SQLite actualiza solo las claves foráneas que apuntaban a `usuarios(legajo)`, sin rehacer tablas), se agregan
  `usuario` (= el legajo como texto, con índice único) y `creado_en`, y `sesiones.legajo` pasa a `usuario_id`. Cada uno
  sigue entrando con su legajo y su contraseña; hasta las sesiones abiertas siguen valiendo.
- Edificios de Mamá ya tiene `usuarios(id, usuario)` y `sesiones(usuario_id)`: no hace falta convertir nada.
- Gestión Automotor tiene `usuarios(legajo)` como UltraMantenimiento: la misma migración.
- Antes de tocar nada, `migrar` copia la base (`<base>_antes_del_nucleo.db`).
- Lo que el módulo hacía al guardar un usuario (UltraMantenimiento: su ficha de Personal) va en
  `nucleo.usuarios.AL_GUARDAR`, y los usuarios que ya existían se sincronizan en `al_iniciar`.
- En el frontend, `S.usuario.legajo` → `S.usuario.id`.

## 5. Datos de ejemplo

El núcleo llama a `datos_iniciales(c)` una vez por base. Para una base que viene de antes del núcleo **no tiene que
cargar nada**: la función mira si ya hay datos (UltraMantenimiento: si hay equipos o personas) y si los hay no hace
nada. Lo que antes se armaba "después de los ejemplos" en el arranque, ahora va al final de `datos_iniciales`, porque
`migrar` corre antes.

## 6. Tests

- `tests/conftest.py`: poner `<PREFIJO>_REPO = ""`, `<PREFIJO>_DB` en una carpeta temporal e **importar `app.main` ahí**,
  antes de cualquier test. `configurar()` fija `db.DB_PATH` al importarse: si un test lo importa después de cambiar
  `DB_PATH`, lo pisa con la base real.
- La fixture: login con `{"usuario": "admin", "password": "admin"}` (el administrador de fábrica del núcleo).
- Lo que ya prueba appbase (actualizador, nombre y logo, puerto) se saca; lo de usuarios se deja solo en lo que hace
  el módulo con ellos.
- Un test de migración: armar una base con el esquema viejo y comprobar que se entra igual y que todo sigue vinculado
  (`tests/test_migracion_nucleo.py` de UltraMantenimiento).

## 7. Probar antes de publicar

1. Los tests de la app.
2. La app sobre la **copia** de la base real: conteos iguales, `PRAGMA foreign_key_check` vacío,
   `PRAGMA integrity_check` = ok, y se creó `<base>_antes_del_nucleo.db`.
3. Las pantallas en el navegador, con la consola: un error de JavaScript al cargar el módulo no se ve en la página
   (Edge headless `--enable-logging=stderr --v=0` muestra los `Uncaught`).
4. Compilar (`herramientas/compilar.py`) y correr el .exe sobre otra copia de la base.
5. Publicar (tag `v<VERSION>`). La versión instalada se actualiza con su actualizador viejo; la migración corre al abrir
   la nueva.
