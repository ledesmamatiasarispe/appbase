# Reglas para trabajar con el núcleo sin romper otras apps

## Dónde va cada cambio

| Qué cambia | Dónde se hace | A quién afecta |
|---|---|---|
| Algo del negocio de una app (el Cronograma de UltraMantenimiento, las pólizas de Gestión Automotor...) | El módulo de esa app, en su repositorio | Solo a esa app |
| Algo de la base (sesión, usuarios, Opciones, actualizador, Ayuda, la página) | **Solo en appbase**, en `nucleo/` | A cada app, **recién cuando la trae** con `sincronizar.py` |

Cada app tiene una copia fija del núcleo (la versión está en su `nucleo/MANIFIESTO.json` y en `apps.json`). Que appbase
cambie no le hace nada a una app hasta que se sincroniza: cada una actualiza cuando le conviene y lo prueba antes.

## Las reglas

1. **El núcleo no se toca dentro de una app.** Si hace falta, el cambio se hace en appbase y se trae.
   `tests/test_nucleo_intacto.py` falla si alguien lo editó a mano, y `sincronizar.py` no pisa un núcleo tocado.

2. **El contrato es lo único que hay que cuidar.** Lo que un módulo puede usar del núcleo está en
   [`docs/contrato.json`](contrato.json), extraído del código (`nucleo/contrato.py`):
   - Python: los nombres públicos de cada archivo del núcleo, con sus firmas (`transaccion`, `validar.*`,
     `ErrorDeNegocio`, `Usuario`/`Admin`, `usuarios.AL_GUARDAR`, `Modulo`, `Menu`, `configurar`...).
   - La API HTTP del núcleo y sus tablas (`usuarios`, `sesiones`, `config`, `archivos`) con sus columnas.
   - JavaScript: lo global de `nucleo.js` (`api`, `VISTAS`, `irA`, `abrirModal`, `enviar`...), `Nucleo.*`, `Ayuda.*`.
   - CSS: las variables de color y las clases de `nucleo.css`.
   - **Lo que empieza con `_` es interno**: un módulo no lo usa y el núcleo lo cambia sin avisar.

3. **Versiones del núcleo con significado** (`VERSION_NUCLEO`):
   - **1.1.x** — arreglos que no tocan el contrato. Se traen sin miedo.
   - **1.x** — se agrega algo (un hook, un parámetro con valor por defecto, una ruta). Nada de lo que había deja de andar.
   - **2.0** — se saca o se cambia algo del contrato. Lleva en `NOVEDADES.md` qué tiene que cambiar cada app.
   `herramientas/contrato.py` no guarda un cambio incompatible sin subir la versión mayor, y `tests/test_contrato.py`
   falla si el contrato no está al día.

4. **Agregar, no cambiar.** Un parámetro nuevo lleva valor por defecto. Si algo se reemplaza, lo viejo convive una
   versión (con un aviso en `NOVEDADES.md`) antes de desaparecer en la siguiente versión mayor.

5. **La base de datos del núcleo solo crece.** Tablas y columnas nuevas con `IF NOT EXISTS` / `db.COLUMNAS`; nunca se
   renombra ni se borra sin una migración que antes copie la base. Nombres que no choquen con los de las apps (por
   eso la tabla de archivos del núcleo se llama `archivos` y no `adjuntos`).

6. **Los módulos no chocan entre sí.** Tablas con nombre propio, rutas bajo `/api/<módulo>/`, y en JavaScript y CSS
   nombres propios. Una constante global repetida hace que el navegador no cargue el archivo y la pantalla falla sin
   mostrar nada: `tests/test_pantallas.py` (lo trae `sincronizar.py`) lo detecta.

7. **Al núcleo solo sube lo que es de todos.** Una herramienta nace en el módulo de su app; si otra app la necesita,
   pasa a `ejemplos/` o a `modulos/` de appbase; solo si es genérica y la usan dos o más apps, al núcleo.

8. **Antes de publicar una app con núcleo nuevo:**
   1. en appbase: tests, `herramientas/contrato.py`, `herramientas/manifiesto.py`, nota en `NOVEDADES.md`, tag
      `nucleo-v<versión>`;
   2. en la app, en una rama: `python <appbase>/herramientas/sincronizar.py <app> --llevar`;
   3. los tests de la app (incluidos `test_nucleo_intacto.py` y `test_pantallas.py`);
   4. abrirla sobre una **copia** de su base y mirar las pantallas con la consola del navegador;
   5. publicar y anotar en `apps.json` qué núcleo usa.

9. **Nunca datos reales en appbase.** La app de ejemplo (`app/` + `modulos/notas`) es el banco de pruebas del núcleo.
   Los datos reales se prueban solo en copias, dentro de cada app.

10. **Tests que no tocan la base real.** `nucleo.configurar()` fija la ruta de la base al importarse `app/main.py`: el
    `conftest.py` de cada app pone `<PREFIJO>_DB` en una carpeta temporal e importa `app.main` antes de cualquier test.

## Mejorar el núcleo, paso a paso

1. Cambiar `nucleo/` con sus tests (`tests/` de appbase, sobre la app de ejemplo).
2. Subir `VERSION_NUCLEO` según la regla 3.
3. `python herramientas/contrato.py` (muestra lo agregado, ampliado, quitado o cambiado) y
   `python herramientas/manifiesto.py`.
4. Anotar en `NOVEDADES.md`.
5. Commit, tag `nucleo-v<versión>`, push. Después, cada app cuando le toque (regla 8).
