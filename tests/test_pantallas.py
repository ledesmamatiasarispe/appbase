"""El chequeo de pantallas (nucleo/chequeo): la app de ejemplo carga limpia, y el chequeo detecta los dos errores que
en el navegador fallan en silencio (los dos ya pasaron al migrar UltraMantenimiento)."""
import pytest

import app.main
from nucleo import chequeo
from nucleo.modulo import Menu, Modulo


def _sin_node(errores):
    if errores is None:
        pytest.skip("No hay Node en esta PC: el chequeo de pantallas no se puede correr.")
    return errores


def test_las_pantallas_de_la_app_cargan_sin_errores():
    assert _sin_node(chequeo.pantallas(app.main.MODULOS)) == []


def _modulo(tmp_path, nombre, codigo, menu=()):
    (tmp_path / nombre / "frontend").mkdir(parents=True)
    (tmp_path / nombre / "frontend" / f"{nombre}.js").write_text(codigo, encoding="utf-8")
    return Modulo(nombre=nombre, carpeta=tmp_path / nombre, scripts=[f"{nombre}.js"], menu=list(menu))


def test_detecta_un_nombre_global_repetido(tmp_path):
    malo = _modulo(tmp_path, "malo", "const MESES = [];\n")   # MESES ya lo declara el núcleo
    errores = _sin_node(chequeo.pantallas([*app.main.MODULOS, malo]))
    assert any("MESES" in e and "already been declared" in e for e in errores), errores


def test_detecta_un_error_al_cargar_y_una_pestana_sin_pantalla(tmp_path):
    viejo = _modulo(tmp_path, "viejo", "Nucleo.algoQueNoExiste.x = 1;\n")   # algo que este núcleo no tiene
    sin_pantalla = _modulo(tmp_path, "vacio", "// no registra VISTAS.vacio\n", menu=[Menu("vacio", "Vacío")])
    errores = _sin_node(chequeo.pantallas([*app.main.MODULOS, viejo, sin_pantalla]))
    assert any("viejo.js" in e and "TypeError" in e for e in errores), errores
    assert any('"vacio" no tiene pantalla' in e for e in errores), errores
