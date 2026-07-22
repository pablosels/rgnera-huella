# -*- coding: utf-8 -*-
"""
Puente IPCC -> SCIAN y multiplicadores de huella para México.

Insumos (100% públicos):
  - MIP 2018 INEGI, subsector SCIAN (78 productos), economía total
    (doméstico+importado), precios básicos: data/mip2018/MIP_6.xlsx
  - Inventario INECC INEGyCEI 2018 por categoría IPCC (tCO2e):
    data/inecc/inegycei_2018.csv

Método: q = Q/x ; A = T·inv(diag(x)) ; L = inv(I-A) ; m = q·L
Unidades: Q en t CO2e, x en millones MXN => q y m en t/M MXN = g CO2e/peso.

Supuestos documentados del puente (afinables):
  A1. [1A3b] Autotransporte 170.8 Mt se reparte 40% hogares (vehículo
      particular, sale del IO y va al factor físico de gasolina), 35%
      autotransporte de carga (484) y 25% pasajeros (485/487).
  A2. [2F] Refrigerantes/aires acondicionados: 30% hogares, 70% repartido
      en todos los sectores proporcional a su producción.
  A3. Bunkers de aviación internacional (6.97 Mt, fuera del total nacional)
      se SUMAN al transporte aéreo 481: el usuario de la calculadora compra
      vuelos internacionales. Se reporta por separado.
  A4. [1A4b] Residencial (gas LP/natural/leña en hogar) -> hogares directo.
  A5. UTCUTS [4] excluido (sumideros de tierra; estándar en huellas).
"""
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# ----------------------------------------------------------------------
# 1. Cargar MIP 2018 subsector (78 productos)
# ----------------------------------------------------------------------
df = pd.ExcelFile(DATA / "mip2018" / "MIP_6.xlsx").parse("Tabulado", header=None)
COL0, COLN = 3, 80          # columnas de los 78 productos
ROW0, ROWN = 6, 83          # filas de los 78 productos
ROW_PROD = 94               # P.1 Producción
COL_CP = 82                 # Consumo privado

codigos = [str(df.iloc[5, c]).split(" - ")[0].strip() for c in range(COL0, COLN + 1)]
nombres = [str(df.iloc[5, c]).split(" - ", 1)[1].strip() for c in range(COL0, COLN + 1)]
assert len(codigos) == 78

T = df.iloc[ROW0:ROWN + 1, COL0:COLN + 1].apply(pd.to_numeric, errors="coerce") \
      .fillna(0.0).to_numpy()
x = pd.to_numeric(df.iloc[ROW_PROD, COL0:COLN + 1], errors="coerce") \
      .fillna(0.0).to_numpy()
cp = pd.to_numeric(df.iloc[ROW0:ROWN + 1, COL_CP], errors="coerce") \
       .fillna(0.0).to_numpy()
filas_lab = [str(df.iloc[r, 0]).split(" - ")[0].strip() for r in range(ROW0, ROWN + 1)]
assert filas_lab == codigos, "orden de filas != columnas"
print(f"[mip] 78 productos; producción total = {x.sum()/1e6:,.2f} billones MXN")

idx = {c: i for i, c in enumerate(codigos)}

# ----------------------------------------------------------------------
# 2. Inventario INECC 2018
# ----------------------------------------------------------------------
inv = pd.read_csv(DATA / "inecc" / "inegycei_2018.csv")
inv["tCO2e"] = pd.to_numeric(inv["emisiones_tCO2e"], errors="coerce")
inv["cat"] = inv["categoria_fuente_subfuente_emision"].astype(str).str.strip()

def E(nombre_contiene):
    sel = inv[inv["cat"].str.contains(nombre_contiene, regex=False)]
    if len(sel) == 0:
        raise KeyError(nombre_contiene)
    return float(sel["tCO2e"].iloc[0])

# ----------------------------------------------------------------------
# 3. Puente: asignaciones
#    destino: código SCIAN, lista de códigos (reparto por x), o "HOGARES"
# ----------------------------------------------------------------------
MANUF = [c for c in codigos if c.startswith("3")]
MANUF_OTRAS = ["313", "314", "315", "316", "321", "323",
               "332", "333", "334", "335", "337", "339"]
SERVICIOS = [c for c in codigos if c >= "431" and not c.startswith("48")]
AGRO = ["111", "112", "113", "114", "115"]

PUENTE = [
    # (categoría INECC exacta, Mt aprox, destino, fracción)
    ("[1A1a] Actividad principal producción de electricidad y calor", "221", 1.0),
    ("[1A1b] Refinación del petróleo",                       "324", 1.0),
    ("1A1ci Fabricación de combustibles sólidos",            "324", 1.0),
    ("1A1cii Otras Industrias de la energía",                "211", 1.0),
    ("[1A2a] Hierro y acero",                                "331", 1.0),
    ("[1A2b] Metales no ferrosos",                           "331", 1.0),
    ("[1A2c] Sustancias químicas",                           "325", 1.0),
    ("[1A2d] Pulpa, papel e imprenta",                       "322", 1.0),
    ("1A2ei elaboración de azúcares",                        "311", 1.0),
    ("1A2eii elaboración de bebidas",                        "312", 1.0),
    ("1A2eiii elaboración de productos de tabaco",           "312", 1.0),
    ("1A2eiiiii elaboración de alimentos",                   "311", 1.0),
    ("[1A2g] Equipo de transporte",                          "336", 1.0),
    ("[1A2i] Minería (con excepción de combustibles)",       "212", 1.0),
    ("[1A2k] Construcción",                                  ["236", "237", "238"], 1.0),
    ("1A2mi Fabricación de vidrio",                          "327", 1.0),
    ("1A2mii Fabricación de productos de hule",              "326", 1.0),
    ("1A2miii Otras ramas",                                  MANUF_OTRAS, 1.0),
    # Transporte (supuesto A1)
    ("[1A3a] Aviación civil",                                "481", 1.0),
    ("[1A3b] Autotransporte",                                "HOGARES", 0.40),
    ("[1A3b] Autotransporte",                                "484", 0.35),
    ("[1A3b] Autotransporte",                                ["485", "487"], 0.25),
    ("[1A3c] Ferrocarriles",                                 "482", 1.0),
    ("[1A3d] Navegación marítima y fluvial",                 "483", 1.0),
    # Otros sectores
    ("[1A4a] Comercial/institucional",                       SERVICIOS, 1.0),
    ("[1A4b] Residencial",                                   "HOGARES", 1.0),
    ("[1A4c] Agropecuario/silvicultura/pesca",               AGRO, 1.0),
    # Fugitivas
    ("[1B1] Combustibles sólidos",                           "212", 1.0),
    ("[1B2] Petróleo y gas natural",                         "211", 1.0),
    # IPPU
    ("[2A] Industria de los minerales",                      "327", 1.0),
    ("[2B] Industria química",                               "325", 1.0),
    ("[2C] Industria de los metales",                        "331", 1.0),
    ("[2D] Uso de productos no energéticos",                 "325", 1.0),
    ("[2E] Industria electrónica",                           "334", 1.0),
    ("[2F] Uso de productos sustitutos",                     "HOGARES", 0.30),  # A2
    ("[2F] Uso de productos sustitutos",                     codigos, 0.70),
    ("[2G] Manufactura y utilización de otros productos",    "335", 1.0),
    ("[2H] Otros",                                           "322", 1.0),
    # Agricultura
    ("[3A] Fermentación entérica",                           "112", 1.0),
    ("[3B] Gestión del estiércol",                           "112", 1.0),
    ("[3C] Cultivo del arroz",                               "111", 1.0),
    ("[3D1] Emisiones directas de los N2O",                  "111", 1.0),
    ("[3D2] Emisiones indirectas de los N2O",                "111", 1.0),
    ("[3F] Emisiones de quemado de biomasa en tierras de cultivo", "111", 1.0),
    ("[3G] Encalado",                                        "111", 1.0),
    ("[3H] aplicación de urea",                              "111", 1.0),
    # Residuos
    ("[5A] Eliminación de residuos sólidos",                 "562", 1.0),
    ("[5B] Tratamiento biológico",                           "562", 1.0),
    ("[5C] Incineración y quema",                            "562", 1.0),
    ("[5D1] Tratamiento y eliminación de aguas residuales municipales", "221", 1.0),
    ("[5D2] Tratamiento y eliminación de aguas residuales industriales", MANUF, 1.0),
    # Bunkers internacionales (supuesto A3, fuera del total nacional)
    ("Aviación internacional",                               "481", 1.0),
]

Q = np.zeros(78)
hogares_directo = 0.0
asignado = 0.0
for cat, destino, frac in PUENTE:
    e = E(cat) * frac
    asignado += e
    if destino == "HOGARES":
        hogares_directo += e
        continue
    if isinstance(destino, str):
        Q[idx[destino]] += e
    else:
        ii = [idx[c] for c in destino]
        w = x[ii] / x[ii].sum()
        for j, iw in zip(ii, w):
            Q[j] += e * iw

bunkers = E("Aviación internacional")
total_nacional = E("EMISIONES Sin UTCUTS")
print(f"[puente] asignado {asignado/1e6:,.1f} Mt (incluye bunkers "
      f"{bunkers/1e6:.1f}); nacional sin UTCUTS = {total_nacional/1e6:,.1f} Mt")
print(f"[puente] sectores: {Q.sum()/1e6:,.1f} Mt | hogares directo: "
      f"{hogares_directo/1e6:,.1f} Mt | cobertura: "
      f"{(Q.sum()+hogares_directo-bunkers)/total_nacional*100:.1f}%")

# ----------------------------------------------------------------------
# 4. Leontief y multiplicadores
# ----------------------------------------------------------------------
xs = np.where(x > 0, x, 1.0)
q = np.where(x > 0, Q / xs, 0.0)          # t/M MXN = g CO2e por peso
A = T / xs[np.newaxis, :]
A[:, x <= 0] = 0.0
L = np.linalg.inv(np.eye(78) - A)
m = q @ L                                  # g CO2e por peso (Scope 3)

out = pd.DataFrame({
    "scian": codigos, "sector": nombres,
    "q_gCO2e_peso": np.round(q, 3), "m_gCO2e_peso": np.round(m, 3),
    "x_MMXN": np.round(x, 0), "consumo_privado_MMXN": np.round(cp, 0),
})
ruta = ROOT / "pipeline" / "sectores_MEX_2018_mip.csv"
out.to_csv(ruta, index=False, encoding="utf-8-sig")

# sanity: huella nacional de consumo privado
huella_cp = float(m @ cp)                  # t CO2e
POB = 125_327_797                          # CONAPO 2018
percap = (huella_cp + hogares_directo) / POB
print(f"\n[sanity] huella consumo privado vía IO: {huella_cp/1e6:,.1f} Mt")
print(f"[sanity] + hogares directo {hogares_directo/1e6:,.1f} Mt => "
      f"per cápita {percap:,.2f} t CO2e/año (esperado ~3-5)")

print(f"\n[ok] {ruta.name}")
print("\nTop 15 multiplicadores (g CO2e por peso):")
print(out.sort_values("m_gCO2e_peso", ascending=False)
      .head(15)[["scian", "sector", "q_gCO2e_peso", "m_gCO2e_peso"]]
      .to_string(index=False, max_colwidth=52))
print("\nSectores de consumo típico:")
for c in ["311", "722", "531", "221", "481", "485", "611", "621", "517"]:
    r = out[out["scian"] == c].iloc[0]
    print(f"  {c} {r['sector'][:45]:47s} m={r['m_gCO2e_peso']:7.2f} g/peso")
