"""El contrato del núcleo (docs/contrato.json) está al día, y la comparación distingue lo compatible de lo que no."""
import json
from pathlib import Path

from nucleo import VERSION_NUCLEO, contrato

GUARDADO = Path(__file__).resolve().parent.parent / "docs" / "contrato.json"


def test_contrato_al_dia():
    guardado = json.loads(GUARDADO.read_text(encoding="utf-8"))
    d = contrato.comparar(guardado, contrato.extraer())
    assert not any(d.values()), f"El contrato cambió: correr python herramientas/contrato.py\n{d}"
    assert guardado["version"] == VERSION_NUCLEO, "Correr python herramientas/contrato.py (cambió VERSION_NUCLEO)"


def test_la_comparacion_separa_lo_compatible_de_lo_que_no():
    viejo = {"version": "1.0.0", "python": {"db": {"transaccion": "()", "conectar": "()", "ahora": "()"}},
             "modulo": {"Modulo": "campos(nombre, carpeta=)"}, "api": ["GET /api/version"]}
    nuevo = {"version": "1.1.0", "python": {"db": {"transaccion": "(modo=)", "conectar": "(ruta)", "nueva": "()"}},
             "modulo": {"Modulo": "campos(nombre, carpeta=, iconos=)"}, "api": ["GET /api/version", "GET /api/otra"]}
    d = contrato.comparar(viejo, nuevo)
    assert d["agregado"] == ["api.GET /api/otra", "python.db.nueva"]
    assert d["quitado"] == ["python.db.ahora"]
    assert d["cambiado"] == ["python.db.conectar"]                         # un parámetro obligatorio nuevo rompe
    assert d["ampliado"] == ["modulo.Modulo", "python.db.transaccion"]     # con valor por defecto, no
