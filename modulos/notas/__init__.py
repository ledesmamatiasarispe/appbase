"""Módulo de ejemplo: NOTAS. Es el molde para hacer un módulo nuevo: copiar esta carpeta, cambiar el nombre y armar lo
propio. Muestra cada pieza del contrato (nucleo/modulo.py):
  - esquema y columnas que se suman después;   - datos de ejemplo la primera vez;
  - casos de uso con sus reglas (servicios.py); - rutas delgadas (rutas.py);
  - pantalla, formulario, "Ver ocultos", una tarjeta en Opciones, la ayuda y un paso del Tour (frontend/notas.js).
"""
from pathlib import Path

from nucleo.modulo import Menu, Modulo

from . import servicios
from .rutas import router

ESQUEMA = """
CREATE TABLE IF NOT EXISTS notas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo     TEXT    NOT NULL,
    texto      TEXT    NOT NULL DEFAULT '',
    prioridad  TEXT    NOT NULL DEFAULT 'normal' CHECK (prioridad IN ('baja', 'normal', 'alta')),
    activa     INTEGER NOT NULL DEFAULT 1,          -- 0 = archivada: sale del listado, no se borra
    creado_por TEXT, creado_en TEXT, modificado_por TEXT, modificado_en TEXT
);
"""

MODULO = Modulo(
    nombre="notas",
    carpeta=Path(__file__).resolve().parent,
    esquema=ESQUEMA,
    columnas=[("notas", "vence", "TEXT")],   # así se suma una columna a una base que ya existía
    datos_iniciales=servicios.datos_iniciales,
    router=router,
    scripts=["notas.js"],
    estilos=["notas.css"],
    menu=[Menu("notas", "Notas", orden=10)],
)
