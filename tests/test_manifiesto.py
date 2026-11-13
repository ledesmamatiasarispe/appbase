"""El manifiesto del núcleo está al día: si se cambió el núcleo, correr herramientas/manifiesto.py (y subir
VERSION_NUCLEO). Es lo que después usan las apps para saber que no tocaron su copia."""
import json

from nucleo import VERSION_NUCLEO, intacto


def test_manifiesto_al_dia():
    assert intacto.cambios() == [], "Correr: python herramientas/manifiesto.py"
    assert json.loads(intacto.MANIFIESTO.read_text(encoding="utf-8"))["version"] == VERSION_NUCLEO
