-- Extraído de Gestión Automotor app/db.py
CREATE TABLE IF NOT EXISTS historial (
    id          INTEGER PRIMARY KEY,
    cuando      TEXT    NOT NULL,
    legajo      INTEGER,
    usuario     TEXT    NOT NULL,
    entidad     TEXT    NOT NULL,          -- cliente, vehiculo, flota, poliza, compania
    entidad_id  INTEGER NOT NULL,
    accion      TEXT    NOT NULL,          -- alta, edicion, baja, reactivacion, eliminacion, venta, foto, pago...
    antes       TEXT,                      -- JSON: solo los campos que cambiaron (o la fila entera al eliminar)
    despues     TEXT                       -- JSON
);
CREATE INDEX IF NOT EXISTS ix_historial_entidad ON historial(entidad, entidad_id);
CREATE TRIGGER IF NOT EXISTS historial_sin_modificar BEFORE UPDATE ON historial
BEGIN SELECT RAISE(ABORT, 'El historial no se modifica'); END;
CREATE TRIGGER IF NOT EXISTS historial_sin_borrar BEFORE DELETE ON historial
BEGIN SELECT RAISE(ABORT, 'El historial no se borra'); END;
