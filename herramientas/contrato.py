"""Actualiza docs/contrato.json (lo que el núcleo ofrece a los módulos y a las apps; ver nucleo/contrato.py).

    python herramientas/contrato.py            muestra qué cambió y, si es compatible, guarda
    python herramientas/contrato.py --ver      solo muestra (no guarda)

Si se QUITÓ o se CAMBIÓ algo (incompatible), no guarda salvo que VERSION_NUCLEO haya subido de versión mayor
(1.x -> 2.0): eso obliga a anotar en NOVEDADES.md lo que cada app tiene que cambiar antes de traer ese núcleo."""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import app.main  # noqa: E402,F401  (configura el núcleo)
from nucleo import contrato  # noqa: E402

DESTINO = RAIZ / "docs" / "contrato.json"


def main() -> None:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    nuevo = contrato.extraer()
    viejo = json.loads(DESTINO.read_text(encoding="utf-8")) if DESTINO.exists() else None
    if viejo:
        d = contrato.comparar(viejo, nuevo)
        for clave, titulo in (("agregado", "Agregado"), ("ampliado", "Ampliado (compatible)"),
                              ("quitado", "QUITADO"), ("cambiado", "CAMBIADO (incompatible)")):
            for x in d[clave]:
                print(f"  {titulo}: {x}")
        incompatible = d["quitado"] or d["cambiado"]
        mayor = lambda v: int(v.split(".")[0])  # noqa: E731
        if incompatible and mayor(nuevo["version"]) <= mayor(viejo["version"]):
            sys.exit(f"\nCambio INCOMPATIBLE con el núcleo {viejo['version']}: subí VERSION_NUCLEO a "
                     f"{mayor(viejo['version']) + 1}.0.0 y anotá en NOVEDADES.md qué tiene que cambiar cada app. No se guardó.")
        if not any(d.values()) and viejo["version"] == nuevo["version"]:
            print("Sin cambios.")
            return
    if "--ver" in sys.argv:
        return
    DESTINO.parent.mkdir(exist_ok=True)
    DESTINO.write_text(json.dumps(nuevo, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Guardado docs/contrato.json (núcleo {nuevo['version']}).")


if __name__ == "__main__":
    main()
