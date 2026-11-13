"""Compara la base (carpeta base/) con una app y, si se pide, copia en un sentido o en el otro.

    python herramientas/sincronizar.py <carpeta de la app>             solo muestra qué difiere (no toca nada)
    python herramientas/sincronizar.py <carpeta de la app> --llevar    copia base/ -> app (la app recibe las mejoras)
    python herramientas/sincronizar.py <carpeta de la app> --traer     copia app -> base/ (una mejora hecha en la app)

La app se reconoce por APP = "..." en su app/version.py, y apps.json dice qué archivos no toma. Después de --llevar,
correr en la app sus tests (tests/test_base.py incluido); después de --traer, llevar la mejora a las otras apps."""
import filecmp
import json
import re
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BASE = RAIZ / "base"


def archivos_base() -> list[str]:
    return sorted(p.relative_to(BASE).as_posix() for p in BASE.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def identificar(app: Path) -> str:
    version = app / "app" / "version.py"
    if not version.is_file():
        sys.exit(f"{app} no parece una app de la base: falta app/version.py.")
    m = re.search(r'^APP\s*=\s*(?:"([^"]+)"|([A-Z_]+))', version.read_text(encoding="utf-8"), re.M)
    if not m:
        sys.exit(f"{version} no define APP: agregarlo (ver README, 'Qué pone cada app').")
    if m.group(1):
        return m.group(1)
    # APP = OTRA_CONSTANTE (Gestión Automotor: APP = EXE_NOMBRE)
    otra = re.search(rf'^{m.group(2)}\s*=\s*"([^"]+)"', version.read_text(encoding="utf-8"), re.M)
    return otra.group(1) if otra else m.group(2)


def main() -> None:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # acentos aunque la consola sea cp1252
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    app = Path(sys.argv[1]).resolve()
    llevar, traer = "--llevar" in sys.argv, "--traer" in sys.argv
    if llevar and traer:
        sys.exit("--llevar o --traer, no los dos.")
    apps = json.loads((RAIZ / "apps.json").read_text(encoding="utf-8"))
    nombre = identificar(app)
    datos = apps.get(nombre)
    if datos is None:
        sys.exit(f"{nombre} no está en apps.json: agregarlo antes.")
    print(f"{datos['nombre']} ({app})")
    distintos = []
    for rel in archivos_base():
        if rel in datos["excluir"]:
            print(f"  {rel:28} (no la toma: tiene la suya)")
            continue
        en_app = app / rel
        if not en_app.exists():
            estado = "FALTA en la app"
        elif filecmp.cmp(BASE / rel, en_app, shallow=False):
            estado = "igual"
        else:
            estado = "DISTINTO"
        print(f"  {rel:28} {estado}")
        if estado != "igual":
            distintos.append(rel)
    if not distintos:
        print("Todo igual.")
        return
    if llevar:
        for rel in distintos:
            (app / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(BASE / rel, app / rel)
        print(f"Copiados a la app: {', '.join(distintos)}. Correr sus tests.")
    elif traer:
        for rel in distintos:
            if (app / rel).exists():
                shutil.copyfile(app / rel, BASE / rel)
        print(f"Traídos a la base: {', '.join(d for d in distintos if (app / d).exists())}. Llevarlos a las otras apps.")
    else:
        print("No se copió nada (--llevar o --traer para copiar).")


if __name__ == "__main__":
    main()
