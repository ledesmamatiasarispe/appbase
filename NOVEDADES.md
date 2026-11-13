# Novedades de la base

## Núcleo 1.1.0 (2026-11-13) — reglas, contrato y chequeo de pantallas

- `docs/reglas.md`: dónde va cada cambio y cómo publicar sin romper otras apps.
- `nucleo/contrato.py` + `docs/contrato.json` + `herramientas/contrato.py`: lo que el núcleo ofrece a los módulos,
  extraído del código. Sacar o cambiar algo exige un núcleo 2.0 (la herramienta no lo guarda si no).
- `nucleo/chequeo`: carga las pantallas sin navegador (Node) y detecta nombres globales repetidos, errores al cargar y
  pestañas sin pantalla. `sincronizar.py` lleva a cada app `tests/test_pantallas.py` (necesita `MODULOS` en `app/main.py`).
- Compatible con 1.0.x: no se sacó ni cambió nada.

## Núcleo 1.0.1 (2026-11-13) — lo que pidió la primera app migrada (UltraMantenimiento 1.1.0)

- La tabla de archivos del núcleo se llama `archivos` (no `adjuntos`): no choca con la tabla propia de una app.
- `configurar(frontend=...)`: la carpeta propia de la app se sirve en `/static/app/` y su `icono.svg` es el ícono de fábrica.
- La pantalla de Usuarios nombra el dato para entrar como diga la app (`LOGIN`: "Legajo", "Usuario"...).
- `Nucleo.pestanas`: qué pestaña del menú se marca en una pantalla que no tiene la suya.
- `docs/migrar_una_app.md` y `ejemplos/migracion_ultramantenimiento/`: la receta para pasar las otras apps.

## Núcleo 1.0.0 (2026-11-13) — la base como app

La base pasa a ser una app que funciona sola (`python -m app`) y sobre la que se construyen las demás con módulos:

- `nucleo/`: lo común, que las apps no modifican (manifiesto + `tests/test_nucleo_intacto.py` en cada app).
- Contrato de módulo (`nucleo/modulo.py`): esquema, columnas nuevas, migración, datos de ejemplo, rutas, scripts,
  estilos, menú, tarjeta en Opciones, ayuda y Tour. `modulos/notas` es el molde.
- La página se arma con el menú y los archivos de cada módulo; la Ayuda recibe los pasos que trae cada módulo.
- Usuarios por nombre de usuario (sirve también un número de legajo); `usuarios.AL_GUARDAR` para que un módulo se entere.
- `ejemplos/`: herramientas de cada app (mapa de planta, horómetro por tramos, importar otra instalación, historial,
  mail semanal, alertas, chequeo de la Ayuda, multiplataforma…).
- `herramientas/compilar.py` genérico (toma APP y VERSION de `app/version.py` y empaqueta el frontend de cada módulo).

## 2026-11-13 — primera versión (archivos compartidos)

Juntado de lo que cada app había hecho por su lado (ahora todo dentro del núcleo):

- **Contraseña provisoria sin bloqueo** (de UltraMantenimiento): banner amarillo hasta cambiarla.
- **Nombre y logo editables** (de UltraMantenimiento).
- **Puerto editable** e **instancia única** (la instancia única venía de Edificios de Mamá; ahora reconoce a la app por
  `/api/version` y no por el puerto, y si el puerto lo usa otro programa toma el siguiente libre).
- **Actualizador**: certificados del sistema + certifi (de Gestión Automotor), copia de la base antes de instalar (de
  Edificios de Mamá, ahora con la API de backup), vuelta atrás si falla la copia del programa en Windows (nuevo).
- **`?v=VERSION` en la página** (de UltraMantenimiento y Edificios de Mamá): sin Ctrl+F5 después de actualizar.
- **Escrituras de a una** (`BEGIN IMMEDIATE`, de Gestión Automotor).
