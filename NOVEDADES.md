# Novedades de la base

## 2026-11-13 — primera versión

Juntado de lo que cada app había hecho por su lado:

- **Contraseña provisoria sin bloqueo** (de UltraMantenimiento): banner amarillo hasta cambiarla en ajustes.
- **Nombre y logo editables** (de UltraMantenimiento).
- **Puerto editable** e **instancia única** (la instancia única venía de Edificios de Mamá; ahora reconoce a la app por
  `/api/version` y no por el puerto, y si el puerto lo usa otro programa toma el siguiente libre).
- **Actualizador**: certificados del sistema + certifi (de Gestión Automotor), copia de la base antes de instalar (de
  Edificios de Mamá, ahora con la API de backup), vuelta atrás si falla la copia del programa en Windows (nuevo).
- **`?v=VERSION` en la página** (de UltraMantenimiento y Edificios de Mamá): sin Ctrl+F5 después de actualizar.
- **Escrituras de a una** (`BEGIN IMMEDIATE`, de Gestión Automotor) en las tres, en el `db.py` de cada una.

Llevado a: UltraMantenimiento 1.0.8, Gestión Automotor APB 0.1.5, Edificios de Mamá 1.2.0 (sin publicar todavía).
