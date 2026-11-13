"""Lleva el núcleo (y, si se pide, módulos reutilizables) de appbase a una app.

    python herramientas/sincronizar.py <carpeta de la app>                     muestra qué cambiaría (no toca nada)
    python herramientas/sincronizar.py <carpeta de la app> --llevar            copia nucleo/ entero a la app
    python herramientas/sincronizar.py <carpeta de la app> --modulo notas      copia también modulos/notas

El núcleo se copia ENTERO (lo que la app tenga en nucleo/ y appbase no, se borra): la app no lo modifica, así que no
hay nada propio que perder. Si la app lo tocó a mano, se avisa y no se copia (hay que llevar ese cambio a appbase
primero). Junto con el núcleo va tests/test_nucleo_intacto.py. Después: correr los tests de la app y publicar."""
import filecmp
import json
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TEST_INTACTO = '''"""El núcleo de esta app es el de appbase, sin cambios a mano. Si falla: el cambio va en appbase y se trae con
herramientas/sincronizar.py (así no se pierde en la próxima sincronización ni se separa de las otras apps)."""
from nucleo import intacto


def test_nucleo_sin_cambios_a_mano():
    assert intacto.cambios() == []
'''


def diferencias(origen: Path, destino: Path) -> list[str]:
    if not destino.exists():
        return ["(no existe en la app)"]
    c = filecmp.dircmp(origen, destino, ignore=["__pycache__"])
    salida = []

    def recorrer(d, prefijo=""):
        salida.extend(f"cambia: {prefijo}{f}" for f in d.diff_files)
        salida.extend(f"nuevo: {prefijo}{f}" for f in d.left_only)
        salida.extend(f"se borra: {prefijo}{f}" for f in d.right_only)
        for nombre, sub in d.subdirs.items():
            recorrer(sub, f"{prefijo}{nombre}/")

    recorrer(c)
    return salida


def tocado_a_mano(app: Path) -> list[str]:
    if not (app / "nucleo" / "intacto.py").exists():
        return []
    r = subprocess.run([sys.executable, "-c", "from nucleo import intacto; print('\\n'.join(intacto.cambios()))"],
                       cwd=app, capture_output=True, text=True)
    return [x for x in r.stdout.splitlines() if x.strip()]


def main() -> None:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # acentos aunque la consola sea cp1252
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    app = Path(sys.argv[1]).resolve()
    llevar = "--llevar" in sys.argv
    modulos = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--modulo" and i + 1 < len(sys.argv)]
    if not (app / "app").is_dir():
        sys.exit(f"{app} no parece una app (falta la carpeta app/).")
    version = json.loads((RAIZ / "nucleo" / "MANIFIESTO.json").read_text(encoding="utf-8"))["version"]
    print(f"Núcleo {version} -> {app}")
    tocado = tocado_a_mano(app)
    if tocado:
        print("  La app MODIFICÓ su núcleo a mano:\n    " + "\n    ".join(tocado))
        print("  Primero llevar esos cambios a appbase (o descartarlos); no se copia nada.")
        sys.exit(1)
    partes = [("nucleo", RAIZ / "nucleo", app / "nucleo")] + [(f"modulos/{m}", RAIZ / "modulos" / m, app / "modulos" / m) for m in modulos]
    for nombre, origen, destino in partes:
        if not origen.is_dir():
            sys.exit(f"No existe {nombre} en appbase.")
        cambios = diferencias(origen, destino)
        print(f"  {nombre}: " + ("igual" if not cambios else "\n    " + "\n    ".join(cambios)))
        if llevar and cambios:
            shutil.rmtree(destino, ignore_errors=True)
            shutil.copytree(origen, destino, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if llevar:
        (app / "modulos").mkdir(exist_ok=True)
        (app / "modulos" / "__init__.py").touch()
        (app / "tests").mkdir(exist_ok=True)
        (app / "tests" / "test_nucleo_intacto.py").write_text(TEST_INTACTO, encoding="utf-8")
        print("Copiado. Correr los tests de la app.")
    else:
        print("No se copió nada (--llevar para copiar).")


if __name__ == "__main__":
    main()
