"""Lo que el asistente (modulos/asistente) sabe de las notas: el molde de una fuente. Si la app no usa el asistente,
esto no hace nada y el módulo funciona igual."""
import re
import unicodedata

from . import servicios


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def responder(pregunta: str) -> dict | None:
    """Sin IA: una cuenta exacta. "¿Cuántas notas hay?" se contesta contando, no se le pregunta a un modelo."""
    if re.search(r"\bcuantas notas\b", _norm(pregunta)):
        notas = [n for n in servicios.listar() if n["activa"]]
        altas = sum(n["prioridad"] == "alta" for n in notas)
        return {"texto": f"Hay {len(notas)} notas vigentes ({altas} de prioridad alta).", "enlaces": [{"texto": "Ver notas", "ir": "notas"}]}
    return None


def contexto(pregunta: str) -> dict | None:
    """Con IA: las notas que comparten palabras con la pregunta, en un texto corto que la IA lee."""
    palabras = {p for p in re.findall(r"[a-z0-9]+", _norm(pregunta)) if len(p) >= 5}   # no "como", "para", "esta"...
    halladas = [n for n in servicios.listar() if palabras & set(re.findall(r"[a-z0-9]+", _norm(n["titulo"] + " " + n["texto"])))]
    if not halladas:
        return None
    lineas = [f"- Nota «{n['titulo']}» (prioridad {n['prioridad']}{', vence ' + n['vence'] if n.get('vence') else ''}): {n['texto'][:300]}"
              for n in halladas[:8]]
    return {"titulo": "Notas", "datos": "NOTAS:\n" + "\n".join(lineas), "resumen": "\n".join(lineas),
            "enlaces": [{"texto": "Ver notas", "ir": "notas"}]}


try:
    from modulos.asistente import Fuente, registrar
except ImportError:
    registrar = None
if registrar:
    registrar(Fuente("notas", responder=responder, contexto=contexto, ejemplos=["¿Cuántas notas hay?"]))
