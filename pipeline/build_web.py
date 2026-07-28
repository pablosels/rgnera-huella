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

logo = (ROOT / "web" / "logo_b64.txt").read_text(encoding="utf-8").strip()
html = plantilla.replace("__DATOS__", json.dumps(datos, ensure_ascii=False)) \
                .replace("__LOGO__", logo)
(DOCS / "index.html").write_text(html, encoding="utf-8")

# banner promocional para la página de inicio (otro Embed en Wix)
banner = (ROOT / "web" / "banner.html").read_text(encoding="utf-8") \
    .replace("__LOGO__", logo)
(DOCS / "banner").mkdir(exist_ok=True)
(DOCS / "banner" / "index.html").write_text(banner, encoding="utf-8")
print(f"[ok] {DOCS/'banner'/'index.html'} ({len(banner):,} bytes)")

# transparencia: publicar también los datos y el CSV de sectores
shutil.copy(ROOT / "web" / "intensidades_MEX.json", DOCS / "intensidades_MEX.json")
shutil.copy(ROOT / "pipeline" / "sectores_MEX_2018_mip.csv", DOCS / "sectores_MEX_2018_mip.csv")
print(f"[ok] {DOCS/'index.html'} ({len(html):,} bytes)")

# rgnera.com/huella/ (sitio nuevo, repo rgnera-web) sirve una COPIA de este
# build: su build.py la toma de aquí e inyecta el canonical. Tras cambiar la
# calculadora: correr `python build.py` en rgnera-web y republicar gh-pages.
if Path(r"C:\Users\minis\rgnera-web").exists():
    print("[nota] recuerda: en rgnera-web corre build.py y republica gh-pages "
          "para actualizar rgnera.com/huella/")
