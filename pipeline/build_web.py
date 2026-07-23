# -*- coding: utf-8 -*-
"""Genera docs/index.html incrustando web/intensidades_MEX.json en la
plantilla web/plantilla.html (sitio autocontenido para GitHub Pages/Wix)."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)

datos = json.loads((ROOT / "web" / "intensidades_MEX.json").read_text(encoding="utf-8"))
plantilla = (ROOT / "web" / "plantilla.html").read_text(encoding="utf-8")

html = plantilla.replace("__DATOS__", json.dumps(datos, ensure_ascii=False))
(DOCS / "index.html").write_text(html, encoding="utf-8")

# transparencia: publicar también los datos y el CSV de sectores
shutil.copy(ROOT / "web" / "intensidades_MEX.json", DOCS / "intensidades_MEX.json")
shutil.copy(ROOT / "pipeline" / "sectores_MEX_2018_mip.csv", DOCS / "sectores_MEX_2018_mip.csv")
print(f"[ok] {DOCS/'index.html'} ({len(html):,} bytes)")
