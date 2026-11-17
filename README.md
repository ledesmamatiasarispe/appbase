# App base

La base común de las apps (UltraMantenimiento, Gestión Automotor APB, Edificios de Mamá…): FastAPI + SQLite +
JavaScript sin framework, una ventana .exe en Windows que se actualiza sola desde GitHub.

**La idea:** las apps se construyen **arriba** de la base sin modificarla. Lo común vive en `nucleo/` y lo propio de
cada negocio en **módulos**. Como cada módulo es autocontenido (sus tablas, rutas, pantallas, menú y ayuda), dos apps
se pueden fusionar activando los módulos de las dos sobre el mismo núcleo.

```
nucleo/       la base: NO se modifica en las apps (tests/test_nucleo_intacto.py lo controla)
modulos/      módulos reutilizables; notas/ es el ejemplo mínimo, el molde para hacer uno nuevo
app/          la app de ejemplo: version.py (su identidad) + main.py (el núcleo + sus módulos)
ejemplos/     herramientas que nacieron en cada app, para reusar (ver ejemplos/README.md)
herramientas/ compilar.py (el .exe y el .zip del release), sincronizar.py, manifiesto.py, contrato.py
docs/         reglas.md (cómo trabajar sin romper otras apps), contrato.json, migrar_una_app.md
tests/        los del núcleo y los del módulo de ejemplo
```

## Probarla

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m app            (http://localhost:8090, usuario admin / admin)
```

## Qué trae el núcleo

| Archivo | Qué hace |
|---|---|
| `ajustes.py` | La identidad de la app (APP, NOMBRE, PREFIJO, PUERTO, VERSION, REPO): la pone la app con `nucleo.configurar(...)`. |
| `db.py` | SQLite: `transaccion()` con `BEGIN IMMEDIATE` (varios usuarios escriben de a uno, sin "database is locked") y reentrante con `SAVEPOINT`; aplica el esquema y las columnas nuevas de cada módulo; administrador inicial `admin`/`admin`. |
| `errores.py`, `validar.py` | `ErrorDeNegocio` (400) y `NoEncontrado` (404); validaciones de campo sobre el texto crudo del formulario. |
| `auth.py`, `usuarios.py` | Sesiones con token, PBKDF2, administrador sí/no; siempre queda un administrador. La contraseña provisoria **no bloquea**: aviso amarillo hasta cambiarla. `usuarios.AL_GUARDAR` avisa a los módulos. |
| `adjuntos.py` | Archivos subidos validados por su contenido (firma), con nombre aleatorio. |
| `marca.py` | Nombre y logo editables desde Opciones. |
| `puerto.py` | Puerto editable; si está ocupado arranca en el siguiente libre; si la app ya estaba abierta, solo abre el navegador. |
| `actualizador.py` | Releases de GitHub: SHA-256, certificados del sistema + certifi (antivirus/proxy), copia de la base antes de instalar, y si la copia del programa falla vuelve a poner el anterior. |
| `modulo.py`, `aplicacion.py`, `arranque.py` | El contrato de un módulo, `crear_app(modulos)` y el `python -m app` / `.exe`. |
| `frontend/` | La página (se arma con el menú y los archivos de cada módulo, con `?v=VERSION`), `nucleo.js` (API, modal, sesión, navegación, Opciones, Usuarios), `ayuda.js` (Ayuda por pantalla y Tour, con los pasos que trae cada módulo) y los estilos. |

## Hacer una app nueva

1. Copiar `nucleo/`, `app/`, `herramientas/`, `.github/`, `requirements*.txt`, `iniciar.bat` y `tests/conftest.py`.
2. En `app/version.py`, su identidad (APP, NOMBRE, PREFIJO, PUERTO, REPO).
3. Hacer sus módulos en `modulos/<nombre>/` copiando `modulos/notas` y listarlos en `app/main.py`.
4. Publicar: subir `VERSION`, crear y empujar el tag `v<VERSION>`; GitHub Actions compila y arma el release.

## Hacer un módulo

Copiar `modulos/notas` (cada archivo explica su parte). Reglas para que los módulos se puedan fusionar:
- tablas con nombre propio, rutas bajo `/api/<módulo>/`, pantallas y funciones de JavaScript con nombre propio;
- las reglas de negocio en `servicios.py` (cada caso de uso, una transacción); las rutas delgadas;
- la ayuda de cada pantalla en `Ayuda.pasos.<vista>` y sus pasos del Tour en `Ayuda.tour`.

## Módulos listos para sumar

- **`modulos/asistente`** — la barra "Preguntá algo" arriba de todo, con micrófono donde el navegador lo permite
  (en el celular, el del teclado). Lo exacto (listas, cuentas, vencimientos) lo contesta la app; lo demás lo redacta una
  IA local (Ollama, sin internet) con los datos que junta cada módulo; sin IA, muestra un resumen. Contesta "ayuda" con
  ejemplos y "¿cómo cargo…?" con los textos de la Ayuda de las pantallas. Cada módulo le enseña lo suyo con una `Fuente`
  (molde: `modulos/notas/asistente.py`): `responder`, `contexto` (con `si_no_figura` para ofrecer cargar lo que falta),
  `sin_resultado` y `ejemplos`; las respuestas pueden traer botones que abren pantallas o formularios del módulo
  (`window.asisAcciones`). Opciones tiene "Reiniciar la IA". Se trae con
  `python herramientas/sincronizar.py <app> --modulo asistente --llevar` y se suma a `MODULOS` en `app/main.py`.
  La IA se instala aparte: Ollama + un modelo chico (`ollama pull qwen2.5:3b`); se configura en Opciones.

## Mejorar el núcleo

**Antes de tocar nada, leer [`docs/reglas.md`](docs/reglas.md)**: dónde va cada cambio, el contrato del núcleo
([`docs/contrato.json`](docs/contrato.json)) y cómo publicar sin romper otras apps.

Se hace **acá**, nunca en una app:
1. Cambiar `nucleo/`, con sus tests, subir `VERSION_NUCLEO` (`nucleo/__init__.py`), correr `herramientas/manifiesto.py`
   y anotar el cambio en `NOVEDADES.md`.
2. Llevarlo a cada app: `python herramientas/sincronizar.py <carpeta de la app> --llevar`, correr sus tests y publicarla.

Una herramienta que nace en una app (por ejemplo, el mapa de planta) se guarda en `ejemplos/` y, cuando la usa más de
una app, pasa a `modulos/` o al núcleo.

## Las apps

| App | Repositorio | Estado |
|---|---|---|
| UltraMantenimiento | `super-duper-lamp` | **sobre el núcleo** desde la 1.1.0 (módulo `mantenimiento`) |
| Gestión Automotor APB | `gestionautomotorapb` | todavía con su base propia; falta pasarla al núcleo |
| Edificios de Mamá | `edificiosDeMama` | todavía con su base propia; falta pasarla al núcleo |

Ver `apps.json`. Para pasar una app al núcleo: **`docs/migrar_una_app.md`** (la receta de UltraMantenimiento).
