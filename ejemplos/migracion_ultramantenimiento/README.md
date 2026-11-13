# Migración de UltraMantenimiento al núcleo (v1.1.0)

Los archivos reales de esa migración, para copiar al migrar otra app. La receta paso a paso: docs/migrar_una_app.md.

- esquema.py: tablas del módulo, migrar() con _migrar_usuarios_al_nucleo (legajo -> id) y datos_iniciales que no carga nada en una base vieja.
- modulo__init__.py: el MODULO (menú, scripts, al_iniciar).
- personal_usuarios.py: engancharse en nucleo.usuarios.AL_GUARDAR.
- app_main.py, app_version.py: la app sobre el núcleo.
- conftest.py: los tests sin tocar la base real (importar app.main antes).
- test_migracion_nucleo.py: base con el esquema viejo -> se entra igual y todo sigue vinculado.
- ayuda_mantenimiento.js: los pasos de la Ayuda y del Tour registrados en el núcleo.
