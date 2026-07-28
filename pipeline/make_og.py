# -*- coding: utf-8 -*-
"""Genera web/og.png (1200x630): la tarjeta que se ve al compartir el link
de la calculadora en WhatsApp/redes. Tipografía y paleta de marca RGNERA."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FCT = Path(r"C:\Users\minis\rgnera-factory\assets")

W, H = 1200, 630
OLIVE, CREAM, GOLD = (71, 83, 35), (245, 241, 230), (233, 203, 141)
AMBER, INK, SAGE = (197, 138, 46), (32, 26, 10), (174, 185, 140)

img = Image.new("RGB", (W, H), OLIVE)
d = ImageDraw.Draw(img)

play = lambda s: ImageFont.truetype(str(FCT / "fonts" / "PlayfairDisplay-Regular.ttf"), s)
popp = lambda s, w="Medium": ImageFont.truetype(str(FCT / "fonts" / f"Poppins-{w}.ttf"), s)

# emblema crema arriba
emb = Image.open(FCT / "emblem_cream.png").convert("RGBA")
emb.thumbnail((96, 96), Image.LANCZOS)
img.paste(emb, ((W - emb.width) // 2, 56), emb)

# marca
mk = popp(22, "Medium")
t = "R G N E R A"
d.text(((W - d.textlength(t, mk)) / 2, 168), t, font=mk, fill=SAGE)

# titular en dos líneas (Playfair)
t1, f1 = "¿Sabes cuál es tu", play(64)
t2, f2 = "huella de carbono?", play(86)
d.text(((W - d.textlength(t1, f1)) / 2, 226), t1, font=f1, fill=CREAM)
d.text(((W - d.textlength(t2, f2)) / 2, 300), t2, font=f2, fill=GOLD)

# pill ámbar con CTA
bt, bf = "Calcúlala en 1 minuto  →", popp(30, "Bold")
bw = d.textlength(bt, bf) + 84
bx, by, bh = (W - bw) / 2, 448, 74
d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh / 2, fill=AMBER)
d.text((bx + 42, by + (bh - 42) / 2), bt, font=bf, fill=INK)

# pie
p, pf = "rgnera.com  ·  gratis, con datos oficiales de México (INEGI + INECC)", popp(21, "Regular")
d.text(((W - d.textlength(p, pf)) / 2, 566), p, font=pf, fill=SAGE)

out = ROOT / "web" / "og.png"
img.save(out, "PNG", optimize=True)
print(f"[ok] {out} ({out.stat().st_size//1024} KB)")
