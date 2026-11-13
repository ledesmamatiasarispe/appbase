# Novedades de la base

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
