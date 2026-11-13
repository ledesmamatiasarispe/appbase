"""Regenera nucleo/MANIFIESTO.json después de cambiar el núcleo (y subir VERSION_NUCLEO en nucleo/__init__.py).

    python herramientas/manifiesto.py

tests/test_manifiesto.py falla si el manifiesto no está al día: así nunca se publica un núcleo sin su manifiesto."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import intacto  # noqa: E402

datos = intacto.generar()
print(f"nucleo {datos['version']}: {len(datos['archivos'])} archivos en el manifiesto.")
