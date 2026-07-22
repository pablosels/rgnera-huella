# -*- coding: utf-8 -*-
"""
Fase 1 — Pipeline de intensidades para la calculadora de huella RGNERA.

Modo 1 (validación, AUS): replica el PersonalSustReport.m del Assignment 2
  (PHYS5033) a partir de T.mat, Q.mat, x.mat, Y.mat y verifica que la huella
  2019 de Pablo dé 49.23 t CO2. Luego exporta las intensidades por categoría.

Modo 2 (producción, MEX u otro país): lee un archivo de multiplicadores de
  Eora (worldmrio.com, hoja 'Multipliers' — Scope 3 en t CO2/US$) y exporta
  las intensidades por categoría para la web.

Salida: web/intensidades_<PAIS>.json con kg CO2(e) por unidad de moneda local.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DROPBOX = Path(r"C:\Users\minis\Dropbox\Sydney Uni\Semestre 2"
               r"\Enviromental Footprints and IO Analysis")
MATDIR = DROPBOX / "Assignment 2 Sustainable Report" / "MATLAB files"

HUELLA_ESPERADA_T = 49.23  # resultado del Written Report 2019 (t CO2e)


def leontief_m(T, Q, x):
    """m = q · L, en (unidad de Q) por (unidad monetaria de x)."""
    q = Q / x
    A = T / x[np.newaxis, :]          # T*inv(diag(x))
    L = np.linalg.inv(np.eye(len(x)) - A)
    return q @ L


def validar_australia():
    import scipy.io as sio
    import pandas as pd

    T = np.asarray(sio.loadmat(MATDIR / "T.mat")["T"], dtype=float)
    Q = np.asarray(sio.loadmat(MATDIR / "Q.mat")["Q"], dtype=float).flatten()
    x = np.asarray(sio.loadmat(MATDIR / "x.mat")["x"], dtype=float).flatten()
    Y = np.asarray(sio.loadmat(MATDIR / "Y.mat")["Y"], dtype=float).flatten()

    m = leontief_m(T, Q, x)           # kt CO2 / M AUD == kg CO2 / AUD
    huella_t = float(m @ Y) * 1000    # kt -> t

    ok = abs(huella_t - HUELLA_ESPERADA_T) < 0.01
    print(f"[validación AUS] huella 2019 = {huella_t:.2f} t CO2 "
          f"(esperado {HUELLA_ESPERADA_T}) -> {'OK' if ok else 'FALLA'}")
    if not ok:
        sys.exit(1)

    labels = pd.ExcelFile(DROPBOX / "Assignment 2 Sustainable Report"
                          / "Sector Labels.xls").parse("Sectors", header=None)
    nombres = [str(v).strip() for v in labels[0].tolist()[2:2 + 344]]
    return m, x, nombres


# Categorías de la calculadora -> sectores de la tabla AUS de 344 sectores
# (índices 1-based del assignment). El promedio del grupo se pondera por x.
CATEGORIAS_AUS = {
    "super":          {"nombre": "Súper y comida en casa",
                       "sectores": [74, 75, 78, 80, 83, 84, 86, 91, 98, 101]},
    "restaurantes":   {"nombre": "Restaurantes y bares", "sectores": [258]},
    "renta":          {"nombre": "Renta / vivienda", "sectores": [294]},
    "electricidad":   {"nombre": "Electricidad", "sectores": [240]},
    "gas":            {"nombre": "Gas (LP / natural)", "sectores": [241]},
    "gasolina":       {"nombre": "Gasolina", "sectores": [139]},
    "transporte_pub": {"nombre": "Transporte público", "sectores": [261]},
    "taxi":           {"nombre": "Taxi / apps de transporte", "sectores": [262]},
    "vuelos":         {"nombre": "Vuelos", "sectores": [268]},
    "ropa":           {"nombre": "Ropa y calzado", "sectores": [118, 119]},
    "electronica":    {"nombre": "Electrónica y tecnología", "sectores": [205]},
    "muebles":        {"nombre": "Muebles y hogar", "sectores": [233, 236]},
    "salud":          {"nombre": "Salud", "sectores": [148, 321, 322]},
    "educacion":      {"nombre": "Educación", "sectores": [320]},
    "telecom":        {"nombre": "Teléfono e internet", "sectores": [281]},
    "entretenimiento": {"nombre": "Entretenimiento",
                        "sectores": [325, 329, 336]},
    "hoteles":        {"nombre": "Hoteles y viajes", "sectores": [259]},
    "servicios":      {"nombre": "Servicios personales", "sectores": [337]},
    "banca":          {"nombre": "Banca y seguros", "sectores": [282, 284]},
}

# Emisiones de combustión directa que el marco IO NO atribuye al usuario
# (mejora del punto 5 del informe). Factores estándar IPCC; el precio por
# unidad convierte $/mes -> unidades físicas y se suma a la parte indirecta.
COMBUSTION_DIRECTA = {
    # kg CO2 por unidad física, y precio típico por unidad en la moneda local
    "gasolina": {"kg_por_unidad": 2.31, "unidad": "litro"},
    "gas":      {"kg_por_unidad": 3.00, "unidad": "kg (gas LP)"},
}


def exportar_aus():
    m, x, nombres = validar_australia()
    cats = {}
    for clave, c in CATEGORIAS_AUS.items():
        ii = [i - 1 for i in c["sectores"]]
        intensidad = float(np.average(m[ii], weights=x[ii]))  # kg CO2/AUD
        cats[clave] = {
            "nombre": c["nombre"],
            "kg_co2_por_unidad_moneda": round(intensidad, 4),
            "sectores": [nombres[i] for i in ii],
        }
    salida = {
        "pais": "Australia",
        "iso3": "AUS",
        "moneda": "AUD",
        "fuente": "Tabla IO 344 sectores PHYS5033 (Assignment 2), Q=CO2 kt",
        "indicador": "CO2",
        "nota": "kg de CO2 por AUD de gasto final; combustión directa aparte",
        "combustion_directa": COMBUSTION_DIRECTA,
        "categorias": cats,
    }
    out = ROOT / "web" / "intensidades_AUS.json"
    out.write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"[exportado] {out}")


def exportar_eora(xlsx, iso3, moneda="USD", indicador="CO2e"):
    """Modo 2: multiplicadores Eora (hoja 'Multipliers', Scope 3 t CO2/US$).

    El mapeo categoría->sectores para el país se define en
    pipeline/categorias_<ISO3>.json una vez que conozcamos su clasificación.
    """
    import pandas as pd
    df = pd.read_excel(xlsx, sheet_name="Multipliers", header=0)
    df.columns = ["pais", "iso3", "entidad", "sector", "scope1", "scope3"]
    df = df[df["scope3"].apply(lambda v: isinstance(v, (int, float)))]
    print(f"[eora] {len(df)} sectores para {iso3}; "
          f"scope3 en t CO2/USD -> kg CO2/USD = x1000")
    mapa_path = ROOT / "pipeline" / f"categorias_{iso3}.json"
    if not mapa_path.exists():
        # sin mapeo aún: volcar los sectores para diseñarlo
        vol = ROOT / "pipeline" / f"sectores_{iso3}.csv"
        df.assign(kg_co2_por_usd=df["scope3"] * 1000).to_csv(
            vol, index=False, encoding="utf-8-sig")
        print(f"[eora] no existe {mapa_path.name}; sectores volcados a "
              f"{vol.name} para diseñar el mapeo")
        return
    mapa = json.loads(mapa_path.read_text(encoding="utf-8"))
    cats = {}
    for clave, c in mapa["categorias"].items():
        sel = df[df["sector"].isin(c["sectores"])]
        if sel.empty:
            print(f"  ! categoría {clave}: ningún sector coincide")
            continue
        cats[clave] = {
            "nombre": c["nombre"],
            "kg_co2_por_unidad_moneda": round(
                float(sel["scope3"].mean()) * 1000 * mapa.get(
                    "usd_por_moneda_local", 1.0), 4),
            "sectores": sel["sector"].tolist(),
        }
    salida = {
        "pais": mapa["pais"], "iso3": iso3, "moneda": moneda,
        "fuente": f"Eora worldmrio multiplicadores Scope 3 ({Path(xlsx).name})",
        "indicador": indicador,
        "combustion_directa": COMBUSTION_DIRECTA,
        "categorias": cats,
    }
    out = ROOT / "web" / f"intensidades_{iso3}.json"
    out.write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"[exportado] {out}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "eora":
        exportar_eora(sys.argv[2], sys.argv[3],
                      *(sys.argv[4:] if len(sys.argv) > 4 else []))
    else:
        exportar_aus()
