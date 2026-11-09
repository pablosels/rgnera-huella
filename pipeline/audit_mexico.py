# -*- coding: utf-8 -*-
"""Auditoría numérica: puente INECC, parseo MIP, Leontief y categorías."""
import io
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

print("=" * 70)
print("A. PUENTE INECC: colisiones de substring y cobertura")
print("=" * 70)
inv = pd.read_csv(DATA / "inecc" / "inegycei_2018.csv")
inv["tCO2e"] = pd.to_numeric(inv["emisiones_tCO2e"], errors="coerce")
inv["cat"] = inv["categoria_fuente_subfuente_emision"].astype(str).str.strip()

PATRONES = [
    "[1A1a] Actividad principal producción de electricidad y calor",
    "[1A1b] Refinación del petróleo",
    "1A1ci Fabricación de combustibles sólidos",
    "1A1cii Otras Industrias de la energía",
    "[1A2a] Hierro y acero", "[1A2b] Metales no ferrosos",
    "[1A2c] Sustancias químicas", "[1A2d] Pulpa, papel e imprenta",
    "1A2ei elaboración de azúcares", "1A2eii elaboración de bebidas",
    "1A2eiii elaboración de productos de tabaco",
    "1A2eiiiii elaboración de alimentos",
    "[1A2g] Equipo de transporte",
    "[1A2i] Minería (con excepción de combustibles)",
    "[1A2k] Construcción", "1A2mi Fabricación de vidrio",
    "1A2mii Fabricación de productos de hule", "1A2miii Otras ramas",
    "[1A3a] Aviación civil", "[1A3b] Autotransporte",
    "[1A3c] Ferrocarriles", "[1A3d] Navegación marítima y fluvial",
    "[1A4a] Comercial/institucional", "[1A4b] Residencial",
    "[1A4c] Agropecuario/silvicultura/pesca",
    "[1B1] Combustibles sólidos", "[1B2] Petróleo y gas natural",
    "[2A] Industria de los minerales", "[2B] Industria química",
    "[2C] Industria de los metales", "[2D] Uso de productos no energéticos",
    "[2E] Industria electrónica", "[2F] Uso de productos sustitutos",
    "[2G] Manufactura y utilización de otros productos", "[2H] Otros",
    "[3A] Fermentación entérica", "[3B] Gestión del estiércol",
    "[3C] Cultivo del arroz", "[3D1] Emisiones directas de los N2O",
    "[3D2] Emisiones indirectas de los N2O",
    "[3F] Emisiones de quemado de biomasa en tierras de cultivo",
    "[3G] Encalado", "[3H] aplicación de urea",
    "[5A] Eliminación de residuos sólidos", "[5B] Tratamiento biológico",
    "[5C] Incineración y quema",
    "[5D1] Tratamiento y eliminación de aguas residuales municipales",
    "[5D2] Tratamiento y eliminación de aguas residuales industriales",
    "Aviación internacional",
]
problemas = 0
for p in PATRONES:
    hits = inv[inv["cat"].str.contains(p, regex=False)]
    if len(hits) != 1:
        print(f"  !! '{p}': {len(hits)} coincidencias:")
        for c in hits["cat"]:
            print(f"       - {c}")
        problemas += 1
print(f"Colisiones/faltantes: {problemas} de {len(PATRONES)} patrones")

# cobertura exacta: suma de hojas asignadas (sin bunkers) vs total nacional
usados = []
for p in PATRONES[:-1]:
    usados.append(float(inv[inv["cat"].str.contains(p, regex=False)]["tCO2e"].iloc[0]))
total_asig = sum(usados)
total_nac = float(inv[inv["cat"] == "EMISIONES Sin UTCUTS"]["tCO2e"].iloc[0])
print(f"Asignado sin bunkers: {total_asig/1e6:.3f} Mt | nacional: {total_nac/1e6:.3f} Mt "
      f"| falta: {(total_nac-total_asig)/1e6:.3f} Mt")

# ¿qué hojas con >0.1 Mt no están cubiertas? construir codigos jerarquicos
def codigo(cat):
    m = re.match(r"\[?([0-9][A-Z0-9()IVi]*[a-z]*)\]?", cat.replace("[", "").strip())
    return m.group(1) if m else None

cods_usados = []
for p in PATRONES[:-1]:
    c = codigo(inv[inv["cat"].str.contains(p, regex=False)]["cat"].iloc[0])
    cods_usados.append(c)
# doble conteo: ningún código usado debe ser prefijo de otro usado
for i, a in enumerate(cods_usados):
    for j, b in enumerate(cods_usados):
        if i != j and a and b and b.startswith(a) and len(b) > len(a):
            print(f"  !! POSIBLE DOBLE CONTEO: '{a}' ({PATRONES[i][:40]}) es "
                  f"prefijo de '{b}' ({PATRONES[j][:40]})")

# hojas grandes sin asignar
print("\nFilas >0.3 Mt cuyo código no está bajo ningún código usado:")
for _, r in inv.iterrows():
    v, cat = r["tCO2e"], r["cat"]
    if pd.isna(v) or abs(v) < 3e5 or cat.startswith("EMISIONES") or "[4" in cat \
       or cat.startswith("Bunkers") or "quema de biomasa" in cat.lower() and "Emisiones de CO2" in cat:
        continue
    c = codigo(cat)
    if not c:
        continue
    cubierto = any(c.startswith(u) or u.startswith(c) for u in cods_usados if u)
    if not cubierto:
        print(f"    {v/1e6:8.3f} Mt | {cat[:70]}")

print()
print("=" * 70)
print("B. MIP: balance UTPB vs Producción y comparación con L de INEGI")
print("=" * 70)
df6 = pd.ExcelFile(DATA / "mip2018" / "MIP_6.xlsx").parse("Tabulado", header=None)
utpb = pd.to_numeric(df6.iloc[6:84, 1], errors="coerce").to_numpy()
prod = pd.to_numeric(df6.iloc[94, 3:81], errors="coerce").to_numpy()
codigos = [str(df6.iloc[5, c]).split(" - ")[0].strip() for c in range(3, 81)]
rel = np.abs(utpb - prod) / np.where(prod != 0, prod, 1)
print(f"max |UTPB - Producción|/Producción = {np.nanmax(rel)*100:.4f}%  "
      f"(mediana {np.nanmedian(rel)*100:.5f}%)")

T = df6.iloc[6:84, 3:81].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy()
x = prod.astype(float)
A = T / np.where(x > 0, x, 1)[np.newaxis, :]
L_tot = np.linalg.inv(np.eye(78) - A)
print(f"radio espectral A: {np.max(np.abs(np.linalg.eigvals(A))):.4f} (<1 ok)")
print(f"L sin negativos: {(L_tot < -1e-9).sum()} entradas negativas")

# L doméstica oficial de INEGI (MIP_27) vs nuestra L total
df27 = pd.ExcelFile(DATA / "mip2018" / "MIP_27.xlsx").parse("Tabulado", header=None)
L_ineg = df27.iloc[6:84, 3:81].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy()
mult_tot = L_tot.sum(axis=0)      # multiplicador de producción total
mult_dom = L_ineg.sum(axis=0)
corr = np.corrcoef(mult_tot, mult_dom)[0, 1]
menor = (mult_tot < mult_dom - 1e-6).sum()
print(f"correlación multiplicadores columna (total vs doméstica INEGI): {corr:.4f}")
print(f"sectores donde total < doméstica (no debería): {menor}")
print(f"promedio mult_total {mult_tot.mean():.3f} vs doméstico {mult_dom.mean():.3f}")

print()
print("=" * 70)
print("C. CATEGORÍAS: recomputar intensidades y defaults vs JSON")
print("=" * 70)
sec = pd.read_csv(ROOT / "pipeline" / "sectores_MEX_2018_mip.csv", dtype={"scian": str}).set_index("scian")
js = json.loads((ROOT / "web" / "intensidades_MEX.json").read_text(encoding="utf-8"))
POB, INFL = js["poblacion"], js["inflacion_a_hoy"]
peor = 0
def default_mes(cat):
    """gasto_default_mxn es anual en los rubros con periodo 'anual'."""
    g = cat["gasto_default_mxn"]
    return g / 12 if cat.get("periodo") == "anual" else g

# defaults fijados a mano (no salen del CP de su sector): físicos o supuestos
MANUALES = ("gasolina", "gas", "electricidad", "res", "cerdo", "apps_comida")
for clave, cat in js["categorias"].items():
    if clave in MANUALES:
        continue
    ss = cat["sectores_scian"]
    sel = sec.loc[[s for s in ss if s in sec.index]]
    w = sel["consumo_privado_MMXN"].clip(lower=0)
    if w.sum() <= 0:
        w = sel["x_MMXN"]
    inten = float((sel["m_gCO2e_peso"] * w).sum() / w.sum()) / 1000
    dflt = float(sel["consumo_privado_MMXN"].clip(lower=0).sum()) * 1e6 / POB / 12 * INFL
    d1 = abs(inten - cat["kg_co2e_por_mxn"])
    d2 = abs(dflt - default_mes(cat))
    if d1 > 1e-5 or d2 > 1:
        print(f"  !! {clave}: inten {inten:.5f} vs {cat['kg_co2e_por_mxn']} | "
              f"default {dflt:.0f} vs {default_mes(cat):.0f}")
        peor += 1
print(f"categorías con discrepancia: {peor}")

# defaults totales vs ENIGH: gasto corriente monetario promedio/persona
tot_def = sum(default_mes(c) for c in js["categorias"].values())
print(f"suma de defaults: {tot_def:,.0f} MXN/mes por persona "
      f"(ENIGH 2022: gasto corriente ~4,200 MXN/pers/mes monetario; "
      f"CP nacional per cápita es mayor por renta imputada y no-monetario)")

# per cápita nacional recalculado
cp = sec["consumo_privado_MMXN"].clip(lower=0).to_numpy()
m = sec["m_gCO2e_peso"].to_numpy()
print(f"huella CP nacional: {(m*cp).sum()/1e6:,.1f} Mt (script reportó 547.0)")
