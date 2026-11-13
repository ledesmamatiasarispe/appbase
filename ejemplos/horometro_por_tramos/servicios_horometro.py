# Extraído de UltraMantenimiento app/servicios.py: lecturas de horómetro, tramos y cambio de horómetro.

def _tramo(c, equipo_id: int, fecha: str | None = None) -> tuple[str, str]:
    """(desde, hasta) del horómetro que estaba puesto en esa fecha (sin fecha: el de ahora); hasta es exclusivo."""
    fecha = fecha or "9999-12-31"
    desde = c.execute("SELECT max(fecha) FROM lecturas_horometro WHERE equipo_id=? AND cambio=1 AND fecha<=?",
                      (equipo_id, fecha)).fetchone()[0]
    hasta = c.execute("SELECT min(fecha) FROM lecturas_horometro WHERE equipo_id=? AND cambio=1 AND fecha>?",
                      (equipo_id, fecha)).fetchone()[0]
    return desde or "0000-01-01", hasta or "9999-12-31"


def _ultima_lectura(c, equipo_id: int) -> sqlite3.Row | None:
    desde, _ = _tramo(c, equipo_id)
    return c.execute("SELECT horas, fecha FROM lecturas_horometro WHERE equipo_id=? AND fecha>=? ORDER BY horas DESC LIMIT 1",
                     (equipo_id, desde)).fetchone()


def _exigir_lectura_coherente(c, equipo_id: int, fecha: str, horas: int) -> None:
    """Un horómetro no retrocede: la lectura no puede ser menor que una anterior ni mayor que una posterior del mismo horómetro."""
    desde, hasta = _tramo(c, equipo_id, fecha)
    antes = c.execute("SELECT max(horas) FROM lecturas_horometro WHERE equipo_id=? AND fecha<=? AND fecha>=?",
                      (equipo_id, fecha, desde)).fetchone()[0]
    despues = c.execute("SELECT min(horas) FROM lecturas_horometro WHERE equipo_id=? AND fecha>? AND fecha<?",
                        (equipo_id, fecha, hasta)).fetchone()[0]
    if antes is not None and horas < antes:
        raise ErrorDeNegocio(f"El horómetro no puede bajar: ya hay una lectura de {antes:,} h en esa fecha o antes.".replace(",", "."))
    if despues is not None and horas > despues:
        raise ErrorDeNegocio(f"Hay una lectura posterior de {despues:,} h: esta no puede ser mayor.".replace(",", "."))


def registrar_lectura(usuario: dict, equipo_id: int, *, fecha, horas, anoto_id=None, observaciones="") -> dict:
    with transaccion() as c:
        eq = _fila(c, "SELECT codigo, usa_horometro FROM equipos WHERE id=?", (equipo_id,), "ese equipo")
        if not eq["usa_horometro"]:
            raise ErrorDeNegocio(f"{eq['codigo']} no tiene horómetro.")
        fecha = _fecha(fecha, "la fecha")
        if fecha > date.today().isoformat():
            raise ErrorDeNegocio("La fecha no puede ser futura.")
        horas = _numero(horas, "el horómetro", entero=True, maximo=10_000_000)
        if horas is None:
            raise ErrorDeNegocio("Falta la lectura del horómetro.")
        _exigir_lectura_coherente(c, equipo_id, fecha, horas)
        c.execute("INSERT INTO lecturas_horometro (equipo_id, fecha, horas, anoto_id, observaciones, creado_por, creado_en) "
                  "VALUES (?,?,?,?,?,?,?)", (equipo_id, fecha, horas, _persona(c, anoto_id, "quién anotó"),
                                             _texto(observaciones, "", False), usuario["nombre"], _ahora()))
        return {"id": c.execute("SELECT last_insert_rowid()").fetchone()[0], "fecha": fecha, "horas": horas}


def cambiar_horometro(usuario: dict, equipo_id: int, *, fecha, horas, horas_anterior=None, anoto_id=None,
                      observaciones="") -> dict:
    """El horómetro se rompió o se reemplazó: desde esa fecha las lecturas son del nuevo, que arranca en `horas`.

    Los servicios por horas no pierden lo que les faltaba: si al B le faltaban 300 h con el horómetro viejo, queda
    a 300 h de lo que marca el nuevo. Lo que marcaba el viejo al sacarlo (`horas_anterior`) es lo más exacto; si no
    se sabe, se usa su última lectura (y las horas trabajadas desde esa lectura se pierden: conviene revisar el Plan).
    Si no hay con qué calcularlo, el servicio queda sin próximo y hay que cargarlo a mano en el Plan."""
    with transaccion() as c:
        eq = _fila(c, "SELECT codigo, usa_horometro FROM equipos WHERE id=?", (equipo_id,), "ese equipo")
        if not eq["usa_horometro"]:
            raise ErrorDeNegocio(f"{eq['codigo']} no tiene horómetro.")
        fecha = _fecha(fecha, "la fecha del cambio")
        if fecha > date.today().isoformat():
            raise ErrorDeNegocio("La fecha no puede ser futura.")
        horas = _numero(horas, "lo que marca el horómetro nuevo", entero=True, maximo=10_000_000)
        if horas is None:
            raise ErrorDeNegocio("Falta lo que marca el horómetro nuevo.")
        if c.execute("SELECT 1 FROM lecturas_horometro WHERE equipo_id=? AND fecha>=?", (equipo_id, fecha)).fetchone():
            raise ErrorDeNegocio("Ya hay lecturas en esa fecha o después: el cambio de horómetro va después de la última lectura.")
        ultima = _ultima_lectura(c, equipo_id)
        anterior = _numero(horas_anterior, "lo que marcaba el horómetro viejo", entero=True, maximo=10_000_000)
        if anterior is not None and ultima and anterior < ultima["horas"]:
            raise ErrorDeNegocio(f"El horómetro viejo ya tenía una lectura de {ultima['horas']:,} h: no pudo marcar menos al sacarlo.".replace(",", "."))
        referencia = anterior if anterior is not None else (ultima["horas"] if ultima else None)
        desde, _ = _tramo(c, equipo_id)
        servicios = []
        for t in c.execute(_SQL_TAREAS + "WHERE t.equipo_id=? AND t.activa=1 AND t.frecuencia=? ORDER BY t.numero",
                           (equipo_id, cal.POR_HORAS)).fetchall():
            hecho = c.execute("SELECT max(horometro) FROM registros WHERE tarea_id=? AND fecha>=? AND resultado IN ('Realizado','Con observaciones')",
                              (t["id"], desde)).fetchone()[0]
            proximo = cal.estado_por_horas(t["cada_horas"], t["proximo_inicial"], referencia, hecho, 0).proximo
            nuevo = horas + (proximo - referencia) if proximo is not None and referencia is not None else None
            c.execute("UPDATE tareas SET proximo_inicial=?, modificado_por=?, modificado_en=? WHERE id=?",
                      (nuevo, usuario["nombre"], _ahora(), t["id"]))
            servicios.append({"codigo": t["codigo"], "seccion": t["seccion"], "antes": proximo, "ahora": nuevo})
        c.execute("INSERT INTO lecturas_horometro (equipo_id, fecha, horas, anoto_id, observaciones, cambio, horas_anterior, "
                  "creado_por, creado_en) VALUES (?,?,?,?,?,1,?,?,?)",
                  (equipo_id, fecha, horas, _persona(c, anoto_id, "quién anotó"), _texto(observaciones, "", False), anterior,
                   usuario["nombre"], _ahora()))
        return {"fecha": fecha, "horas": horas, "referencia": referencia, "servicios": servicios}


