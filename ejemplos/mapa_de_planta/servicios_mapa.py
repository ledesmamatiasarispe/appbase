# Extraído de UltraMantenimiento app/servicios.py (backend del mapa de planta).

# ── mapa de planta ──
MAX_ELEMENTOS = 2000
COLORES_PLANO = ("gris", "azul", "verde", "ambar", "rojo")
MAX_LADO_PLANO = 5000   # metros


def _numero_obligatorio(valor, campo: str, **kw) -> float:
    n = _numero(valor, campo, **kw)
    if n is None:
        raise ErrorDeNegocio(f"Falta {campo}.")
    return n


def _medidas_plano(ancho, alto) -> tuple[float, float]:
    return (_numero_obligatorio(ancho, "el ancho", minimo=1, maximo=MAX_LADO_PLANO),
            _numero_obligatorio(alto, "el alto", minimo=1, maximo=MAX_LADO_PLANO))


def _validar_elementos(elementos, ancho: float, alto: float) -> list[dict]:
    """Lo dibujado: rect (x, y, w, h, etiqueta), linea (x1, y1, x2, y2) y texto (x, y, texto, tamanio). Todo en metros,
    dentro del plano, y el color de una lista fija: el dibujo se arma con estos datos y no admite nada más."""
    if not isinstance(elementos, list):
        raise ErrorDeNegocio("El dibujo del plano no es válido.")
    if len(elementos) > MAX_ELEMENTOS:
        raise ErrorDeNegocio(f"El plano puede tener hasta {MAX_ELEMENTOS} elementos dibujados.")

    def coord(el, k, maximo, minimo=0.0):
        return _numero_obligatorio(el.get(k), "una medida del dibujo", minimo=minimo, maximo=maximo)

    salida = []
    for el in elementos:
        if not isinstance(el, dict):
            raise ErrorDeNegocio("El dibujo del plano no es válido.")
        tipo, color = el.get("tipo"), el.get("color") or "gris"
        if color not in COLORES_PLANO:
            raise ErrorDeNegocio("Color no válido en el dibujo.")
        if tipo == "rect":
            x, y = coord(el, "x", ancho), coord(el, "y", alto)
            w, h = coord(el, "w", ancho - x, 0.01), coord(el, "h", alto - y, 0.01)
            salida.append({"tipo": tipo, "x": x, "y": y, "w": w, "h": h, "color": color,
                           "etiqueta": _corto(el.get("etiqueta"), 60)})
        elif tipo == "linea":
            salida.append({"tipo": tipo, "x1": coord(el, "x1", ancho), "y1": coord(el, "y1", alto),
                           "x2": coord(el, "x2", ancho), "y2": coord(el, "y2", alto), "color": color})
        elif tipo == "texto":
            texto = _corto(el.get("texto"), 80)
            if not texto:
                raise ErrorDeNegocio("Un texto del plano está vacío.")
            salida.append({"tipo": tipo, "x": coord(el, "x", ancho), "y": coord(el, "y", alto), "texto": texto, "color": color,
                           "tamanio": _numero(el.get("tamanio") or 1, "el tamaño del texto", entero=True, minimo=1, maximo=5)})
        else:
            raise ErrorDeNegocio("El dibujo del plano tiene un elemento desconocido.")
    return salida


def _estado_equipos(hoy: date | None = None) -> dict[str, dict]:
    """Por código de equipo: lo que tiene pendiente (lo mismo que Inicio) y el peor estado, para el color del punto."""
    p = pendientes(hoy)
    meses = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
    salida: dict[str, dict] = {}

    def anotar(codigo, estado, item):
        e = salida.setdefault(codigo, {"estado": "al_dia", "pendientes": []})
        e["pendientes"].append({**item, "estado": estado})
        if _PEOR[estado] > _PEOR[e["estado"]]:
            e["estado"] = estado

    for t in p["atrasados"]:
        anotar(t["equipo_codigo"], "vencido", {"tarea_id": t["tarea_id"], "codigo": t["codigo"], "seccion": t["seccion"],
                                               "detalle": f"Atrasada de {meses[t['mes'] - 1]}"})
    for t in p["este_mes"]:
        anotar(t["equipo_codigo"], "pendiente", {"tarea_id": t["tarea_id"], "codigo": t["codigo"], "seccion": t["seccion"],
                                                 "detalle": "Toca este mes"})
    for s in p["por_horas"]:
        estado = {"vencido": "vencido", "proximo": "pendiente"}.get(s["estado"], "sin_dato")
        detalle = (f"Vencido por {-s['faltan']} h" if s["estado"] == "vencido" else f"Faltan {s['faltan']} h" if s["estado"] == "proximo"
                   else "Sin lectura de horómetro" if s["estado"] == "sin_lectura" else "Falta el próximo inicial en el Plan")
        anotar(s["equipo_codigo"], estado, {"tarea_id": s["tarea_id"], "codigo": s["codigo"], "seccion": s["seccion"],
                                            "detalle": detalle})
    return salida


_PEOR = {"al_dia": 0, "sin_dato": 1, "pendiente": 2, "vencido": 3}


def _plano(r) -> dict:
    return {"id": r["id"], "nombre": r["nombre"], "ancho": r["ancho"], "alto": r["alto"], "elementos": json.loads(r["elementos"])}


def mapa_planta(hoy: date | None = None) -> dict:
    """Los planos con lo dibujado, y cada equipo vigente con su ubicación (si la tiene) y su estado de mantenimiento."""
    estados = _estado_equipos(hoy)
    with transaccion() as c:
        planos = [_plano(r) for r in c.execute("SELECT * FROM planos ORDER BY nombre")]
        equipos = c.execute("SELECT e.id, e.codigo, e.nombre, coalesce(a.nombre, '') AS sector, e.plano_id, e.plano_x, e.plano_y "
                            "FROM equipos e LEFT JOIN areas a ON a.id = e.area_id WHERE e.activo=1 ORDER BY e.codigo").fetchall()
    return {"planos": planos,
            "equipos": [{**dict(e), **estados.get(e["codigo"], {"estado": "al_dia", "pendientes": []})} for e in equipos]}


def crear_plano(usuario: dict, *, nombre, ancho, alto) -> dict:
    nombre = _corto(_texto(nombre, "el nombre del plano"), 60)
    ancho, alto = _medidas_plano(ancho, alto)
    with transaccion() as c:
        if c.execute("SELECT 1 FROM planos WHERE nombre=?", (nombre,)).fetchone():
            raise ErrorDeNegocio(f"Ya hay un plano '{nombre}'.")
        c.execute("INSERT INTO planos (nombre, ancho, alto, creado_por, creado_en) VALUES (?,?,?,?,?)",
                  (nombre, ancho, alto, usuario["nombre"], _ahora()))
        return _plano(c.execute("SELECT * FROM planos WHERE id=last_insert_rowid()").fetchone())


def guardar_plano(usuario: dict, plano_id: int, *, nombre, ancho, alto, elementos, equipos) -> dict:
    """Guarda el plano entero: medidas, dibujo y qué máquinas están en él y dónde. Una máquina que estaba en este plano
    y ya no viene queda sin ubicar; una que estaba en otro plano se muda a este (una máquina está en un solo lugar)."""
    nombre = _corto(_texto(nombre, "el nombre del plano"), 60)
    ancho, alto = _medidas_plano(ancho, alto)
    elementos = _validar_elementos(elementos, ancho, alto)
    if not isinstance(equipos, list):
        raise ErrorDeNegocio("La lista de máquinas del plano no es válida.")
    puntos: dict[int, tuple[float, float]] = {}
    for p in equipos:
        if not isinstance(p, dict):
            raise ErrorDeNegocio("La lista de máquinas del plano no es válida.")
        eid = _numero_obligatorio(p.get("equipo_id"), "el equipo", entero=True, minimo=1)
        puntos[eid] = (_numero_obligatorio(p.get("x"), "la ubicación de la máquina", maximo=ancho),
                       _numero_obligatorio(p.get("y"), "la ubicación de la máquina", maximo=alto))
    with transaccion() as c:
        _fila(c, "SELECT id FROM planos WHERE id=?", (plano_id,), "ese plano")
        if c.execute("SELECT 1 FROM planos WHERE nombre=? AND id<>?", (nombre, plano_id)).fetchone():
            raise ErrorDeNegocio(f"Ya hay un plano '{nombre}'.")
        for eid in puntos:
            e = _fila(c, "SELECT codigo, activo FROM equipos WHERE id=?", (eid,), "ese equipo")
            if not e["activo"]:
                raise ErrorDeNegocio(f"{e['codigo']} está obsoleto: no se ubica en el mapa.")
        c.execute("UPDATE planos SET nombre=?, ancho=?, alto=?, elementos=?, modificado_por=?, modificado_en=? WHERE id=?",
                  (nombre, ancho, alto, json.dumps(elementos, ensure_ascii=False), usuario["nombre"], _ahora(), plano_id))
        c.execute("UPDATE equipos SET plano_id=NULL, plano_x=NULL, plano_y=NULL WHERE plano_id=?", (plano_id,))
        for eid, (x, y) in puntos.items():
            c.execute("UPDATE equipos SET plano_id=?, plano_x=?, plano_y=? WHERE id=?", (plano_id, x, y, eid))
        return _plano(c.execute("SELECT * FROM planos WHERE id=?", (plano_id,)).fetchone())


def eliminar_plano(usuario: dict, plano_id: int) -> None:
    """Es solo un dibujo: borrarlo deja sus máquinas sin ubicar y no toca nada de su historial."""
    with transaccion() as c:
        _fila(c, "SELECT id FROM planos WHERE id=?", (plano_id,), "ese plano")
        c.execute("UPDATE equipos SET plano_id=NULL, plano_x=NULL, plano_y=NULL WHERE plano_id=?", (plano_id,))
        c.execute("DELETE FROM planos WHERE id=?", (plano_id,))


