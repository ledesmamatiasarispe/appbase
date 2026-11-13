-- Extraído de UltraMantenimiento app/db.py
-- Mapa de planta: cada plano es un dibujo (rectángulos, líneas, textos) en metros. Las máquinas se ubican como puntos
-- con equipos.plano_id/plano_x/plano_y: una máquina está en un solo plano.
CREATE TABLE IF NOT EXISTS planos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre     TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    ancho      REAL    NOT NULL,
    alto       REAL    NOT NULL,
    elementos  TEXT    NOT NULL DEFAULT '[]',          -- JSON: lo dibujado (ver servicios._validar_elementos)
    creado_por TEXT, creado_en TEXT, modificado_por TEXT, modificado_en TEXT
);
-- y en equipos: plano_id INTEGER REFERENCES planos(id), plano_x REAL, plano_y REAL
