"""Casos de uso de las notas. Cada uno es UNA transacción completa; las reglas viven acá, no en las rutas ni en la
pantalla. Los valores llegan crudos del formulario y se validan con nucleo.validar."""
from nucleo import validar
from nucleo.db import ahora, transaccion
from nucleo.errores import ErrorDeNegocio

PRIORIDADES = ("baja", "normal", "alta")
_CLAVE_MOSTRAR = "notas_mostrar_archivadas_en_inicio"


def _datos(d: dict) -> tuple:
    return (validar.texto(d.get("titulo"), "el título", maximo=120), validar.corto(d.get("texto"), 4000),
            validar.opcion(d.get("prioridad") or "normal", PRIORIDADES, "la prioridad"),
            validar.fecha(d.get("vence"), "el vencimiento", obligatorio=False))


def listar() -> list[dict]:
    with transaccion() as c:
        return [dict(r) for r in c.execute("SELECT * FROM notas ORDER BY activa DESC, "
                                           "CASE prioridad WHEN 'alta' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, id DESC")]


def crear(usuario: dict, **datos) -> dict:
    titulo, texto, prioridad, vence = _datos(datos)
    with transaccion() as c:
        c.execute("INSERT INTO notas (titulo, texto, prioridad, vence, creado_por, creado_en) VALUES (?,?,?,?,?,?)",
                  (titulo, texto, prioridad, vence, usuario["nombre"], ahora()))
        return dict(c.execute("SELECT * FROM notas WHERE id=last_insert_rowid()").fetchone())


def actualizar(usuario: dict, nota_id: int, **datos) -> dict:
    titulo, texto, prioridad, vence = _datos(datos)
    with transaccion() as c:
        n = validar.fila(c, "SELECT activa FROM notas WHERE id=?", (nota_id,), "esa nota")
        if not n["activa"]:
            raise ErrorDeNegocio("La nota está archivada: reactivarla antes de editarla.")
        c.execute("UPDATE notas SET titulo=?, texto=?, prioridad=?, vence=?, modificado_por=?, modificado_en=? WHERE id=?",
                  (titulo, texto, prioridad, vence, usuario["nombre"], ahora(), nota_id))
        return dict(c.execute("SELECT * FROM notas WHERE id=?", (nota_id,)).fetchone())


def cambiar_alta(usuario: dict, nota_id: int, *, activa: bool) -> dict:
    """Archivar no borra: la nota sale del listado y se ve con "Ver ocultos"."""
    with transaccion() as c:
        validar.fila(c, "SELECT id FROM notas WHERE id=?", (nota_id,), "esa nota")
        c.execute("UPDATE notas SET activa=?, modificado_por=?, modificado_en=? WHERE id=?",
                  (int(activa), usuario["nombre"], ahora(), nota_id))
        return dict(c.execute("SELECT * FROM notas WHERE id=?", (nota_id,)).fetchone())


def datos_iniciales(c) -> None:
    """Ejemplos INVENTADOS, una sola vez por base (los llama el núcleo dentro de su transacción)."""
    for titulo, texto, prioridad in (("Bienvenida", "Esta es una nota de ejemplo. Se puede editar o archivar.", "normal"),
                                     ("Probar la Ayuda", "Tocá Ayuda arriba a la derecha para ver cómo se usa esta pantalla.", "alta")):
        c.execute("INSERT INTO notas (titulo, texto, prioridad, creado_por, creado_en) VALUES (?,?,?,'Ejemplo',?)",
                  (titulo, texto, prioridad, ahora()))
