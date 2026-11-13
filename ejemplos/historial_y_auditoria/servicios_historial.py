# Extraído de Gestión Automotor app/servicios.py: historial append-only y escritura auditada.

# ── historial y escritura auditada ──────────────────────────────────────────

_AUDITORIA = ("creado_por", "creado_en", "modificado_por", "modificado_en")


def _json(d) -> str | None:
    return None if d is None else json.dumps(d, ensure_ascii=False, default=str)


def _sin_auditoria(fila) -> dict:
    return {k: fila[k] for k in fila.keys() if k not in _AUDITORIA}


def _registrar(c, usuario: dict, entidad: str, entidad_id: int, accion: str, antes=None, despues=None) -> None:
    """Un renglón del historial. Usarlo directo solo para eventos que no son una fila (una venta, un pago...);
    para altas/ediciones/eliminaciones ya lo hacen _insertar/_actualizar/_borrar."""
    c.execute("INSERT INTO historial (cuando, legajo, usuario, entidad, entidad_id, accion, antes, despues) "
              "VALUES (?,?,?,?,?,?,?,?)",
              (_ahora(), usuario.get("legajo"), usuario["nombre"], entidad, entidad_id, accion, _json(antes), _json(despues)))


def _insertar(c, usuario: dict, tabla: str, datos: dict, entidad: str | None, accion: str = "alta",
              entidad_id: int | None = None) -> int:
    """INSERT con auditoría. Si hay `entidad`, deja en el historial (entidad, entidad_id o el id nuevo, accion)
    con los datos cargados. `tabla` y las claves de `datos` las escribe el código, nunca el usuario."""
    ahora = _ahora()
    fila = {**datos, "creado_por": usuario["nombre"], "creado_en": ahora,
            "modificado_por": usuario["nombre"], "modificado_en": ahora}
    nuevo = c.execute(f"INSERT INTO {tabla} ({', '.join(fila)}) VALUES ({', '.join('?' * len(fila))})",
                      tuple(fila.values())).lastrowid
    if entidad:
        _registrar(c, usuario, entidad, entidad_id or nuevo, accion, None, {"id": nuevo, **datos})
    return nuevo


def _actualizar(c, usuario: dict, tabla: str, fila_id: int, cambios: dict, entidad: str | None,
                accion: str = "edicion", entidad_id: int | None = None) -> dict:
    """UPDATE con auditoría, solo de lo que de verdad cambió. Devuelve {campo: (antes, después)};
    vacío si no cambió nada (y entonces no escribe ni deja historial)."""
    actual = c.execute(f"SELECT * FROM {tabla} WHERE id=?", (fila_id,)).fetchone()
    if not actual:
        raise NoEncontrado(f"No existe ese registro ({tabla} {fila_id}).")
    distintos = {k: (actual[k], v) for k, v in cambios.items() if actual[k] != v}
    if not distintos:
        return {}
    sets = {**{k: v for k, (_, v) in distintos.items()}, "modificado_por": usuario["nombre"], "modificado_en": _ahora()}
    c.execute(f"UPDATE {tabla} SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?", (*sets.values(), fila_id))
    if entidad:
        _registrar(c, usuario, entidad, entidad_id or fila_id, accion,
                   {k: a for k, (a, _) in distintos.items()}, {k: d for k, (_, d) in distintos.items()})
    return distintos


def _borrar(c, usuario: dict, tabla: str, fila_id: int, entidad: str | None, accion: str = "eliminacion",
            entidad_id: int | None = None) -> None:
    """DELETE que deja en el historial la fila entera tal como era."""
    actual = c.execute(f"SELECT * FROM {tabla} WHERE id=?", (fila_id,)).fetchone()
    if not actual:
        return
    c.execute(f"DELETE FROM {tabla} WHERE id=?", (fila_id,))
    if entidad:
        _registrar(c, usuario, entidad, entidad_id or fila_id, accion, _sin_auditoria(actual), None)


def _historial(c, entidad: str, entidad_id: int) -> list[dict]:
    filas = c.execute("SELECT * FROM historial WHERE entidad=? AND entidad_id=? ORDER BY id DESC", (entidad, entidad_id))
    return [{**dict(r), "antes": json.loads(r["antes"]) if r["antes"] else None,
             "despues": json.loads(r["despues"]) if r["despues"] else None} for r in filas]


ENTIDADES = ("cliente", "vehiculo", "flota", "poliza", "compania", "documento", "documento_tipo", "opciones")


def historial(entidad: str, entidad_id: int) -> list[dict]:
    _opcion(entidad, list(ENTIDADES), "la entidad")
    with transaccion() as c:
        return _historial(c, entidad, entidad_id)
