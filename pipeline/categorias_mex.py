# -*- coding: utf-8 -*-
"""
Mapeo de categorías de la calculadora -> subsectores SCIAN y generación de
web/intensidades_MEX.json.

- Intensidad de cada categoría = promedio de m (g CO2e/peso, Scope 3, MIP
  2018 + INEGyCEI) ponderado por el CONSUMO PRIVADO de cada subsector
  (columna CP de la propia MIP): pondera como realmente gastan los hogares.
- Gasto default por categoría = consumo privado per cápita mensual 2018,
  escalado a pesos corrientes con un factor de inflación configurable.
- Energía directa (electricidad, gasolina, gas LP) se maneja con factores
  físicos; la parte de cadena de suministro (upstream) se suma aparte.
"""
import io
import json
import sys
from pathlib import Path

import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent

POB_2018 = 125_327_797
INFLACION_2018_2026 = 1.47      # INPC aprox jul-2018 -> jul-2026; ajustable

# Factores físicos de combustión directa (verificar en auditoría)
FISICOS = {
    "electricidad": {"factor": 0.435, "unidad": "kg CO2e por kWh",
                     "fuente": "Factor de emisión del Sistema Eléctrico "
                               "Nacional (SEMARNAT/CRE), más reciente",
                     "precio_default_mxn": 1.8},
    "gasolina": {"factor": 2.31, "unidad": "kg CO2 por litro",
                 "fuente": "IPCC 2006 gasolina automotriz",
                 "precio_default_mxn": 24.0},
    "gas_lp": {"factor": 1.66, "unidad": "kg CO2 por litro",
               "fuente": "IPCC 2006 GLP (2.98 kg/kg, densidad 0.54)",
               "precio_default_mxn": 12.0},
}

CATEGORIAS = {
    "super": {
        "nombre": "Súper y comida en casa",
        "pregunta": "¿Cuánto gastas al mes en súper, mercado y despensa?",
        "sectores": ["311", "312", "111", "112", "114"],
    },
    "restaurantes": {
        "nombre": "Restaurantes, cafés y bares",
        "pregunta": "¿Cuánto gastas al mes en comer y beber fuera?",
        "sectores": ["722"],
    },
    "renta": {
        "nombre": "Renta o vivienda",
        "pregunta": "¿Cuánto pagas de renta al mes (o valor equivalente)?",
        "sectores": ["531"],
    },
    "electricidad": {
        "nombre": "Electricidad (recibo CFE)",
        "pregunta": "¿De cuánto es tu recibo de luz mensual (o kWh)?",
        "fisico": "electricidad",
        "sectores": ["221"],
    },
    "gasolina": {
        "nombre": "Gasolina",
        "pregunta": "¿Cuánto gastas de gasolina al mes?",
        "fisico": "gasolina",
        "sectores": ["324"],
    },
    "gas": {
        "nombre": "Gas LP / natural",
        "pregunta": "¿Cuánto gastas de gas al mes?",
        "fisico": "gas_lp",
        "sectores": ["221"],
    },
    "transporte_publico": {
        "nombre": "Transporte público",
        "pregunta": "¿Cuánto gastas al mes en metro, camión, combi?",
        "sectores": ["485"],
    },
    "taxi_apps": {
        "nombre": "Taxi y apps (Uber, Didi)",
        "pregunta": "¿Cuánto gastas al mes en taxis o apps de transporte?",
        "sectores": ["485"],
    },
    "vuelos": {
        "nombre": "Vuelos",
        "pregunta": "¿Cuánto gastas en vuelos al mes (promedia tu año)?",
        "sectores": ["481"],
    },
    "ropa": {
        "nombre": "Ropa y calzado",
        "pregunta": "¿Cuánto gastas al mes en ropa y zapatos?",
        "sectores": ["315", "316", "313", "314"],
    },
    "electronica": {
        "nombre": "Electrónica y tecnología",
        "pregunta": "¿Cuánto gastas al mes en celular, cómputo, gadgets?",
        "sectores": ["334"],
    },
    "hogar": {
        "nombre": "Muebles y artículos del hogar",
        "pregunta": "¿Cuánto gastas al mes en muebles, electrodomésticos, hogar?",
        "sectores": ["337", "335", "339"],
    },
    "salud": {
        "nombre": "Salud y medicinas",
        "pregunta": "¿Cuánto gastas al mes en médicos, hospital y farmacia?",
        "sectores": ["621", "622", "623", "624", "325"],
    },
    "educacion": {
        "nombre": "Educación",
        "pregunta": "¿Cuánto gastas al mes en colegiaturas y cursos?",
        "sectores": ["611"],
    },
    "telecom": {
        "nombre": "Teléfono, internet y streaming",
        "pregunta": "¿Cuánto gastas al mes en celular, internet y plataformas?",
        "sectores": ["517", "518", "515", "519"],
    },
    "entretenimiento": {
        "nombre": "Entretenimiento y deporte",
        "pregunta": "¿Cuánto gastas al mes en cine, conciertos, gym, deporte?",
        "sectores": ["711", "712", "713", "512"],
    },
    "hoteles": {
        "nombre": "Hoteles y viajes",
        "pregunta": "¿Cuánto gastas al mes en hospedaje y tours (promedia)?",
        "sectores": ["721", "487"],
    },
    "personales": {
        "nombre": "Servicios personales",
        "pregunta": "¿Cuánto gastas al mes en estética, tintorería, etc.?",
        "sectores": ["812"],
    },
    "otros": {
        "nombre": "Otros gastos",
        "pregunta": "¿Cuánto más gastas al mes (aprox.) en todo lo demás?",
        "sectores": "RESTO",   # promedio CP-ponderado de sectores no cubiertos
    },
}


def main():
    df = pd.read_csv(ROOT / "pipeline" / "sectores_MEX_2018_mip.csv",
                     dtype={"scian": str})
    df = df.set_index("scian")

    cubiertos = set()
    for c in CATEGORIAS.values():
        if isinstance(c["sectores"], list):
            cubiertos.update(c["sectores"])

    salida = {"pais": "México", "iso3": "MEX", "moneda": "MXN",
              "anio_base": 2018, "poblacion": POB_2018,
              "inflacion_a_hoy": INFLACION_2018_2026,
              "fuente": "MIP 2018 INEGI (78 subsectores SCIAN, precios "
                        "básicos) + INEGyCEI 2018 INECC (tCO2e). "
                        "Metodología Leontief EEIO; véase pipeline/.",
              "unidad_intensidad": "kg CO2e por MXN (de 2018)",
              "fisicos": FISICOS, "categorias": {}}

    for clave, c in CATEGORIAS.items():
        if c["sectores"] == "RESTO":
            sel = df[~df.index.isin(cubiertos)]
        else:
            sel = df.loc[[s for s in c["sectores"] if s in df.index]]
        w = sel["consumo_privado_MMXN"].clip(lower=0)
        if w.sum() <= 0:
            w = sel["x_MMXN"]
        inten_g_peso = float((sel["m_gCO2e_peso"] * w).sum() / w.sum())
        cp_total_mmxn = float(sel["consumo_privado_MMXN"].clip(lower=0).sum())
        default_mes = cp_total_mmxn * 1e6 / POB_2018 / 12 * INFLACION_2018_2026

        kg_por_mxn = inten_g_peso / 1000

        # Combustibles: en modo pesos la intensidad correcta es
        # combustión física + cadena de producción, no el sector IO
        # (gas comparte columna con electricidad; gasolina IO no incluye
        # quemarla). Precio en pesos DE 2018 para consistencia con m.
        if clave == "gasolina":
            m324 = float(df.loc["324", "m_gCO2e_peso"]) / 1000
            precio_2018, precio_basico_2018 = 19.0, 10.0
            kg_por_mxn = (FISICOS["gasolina"]["factor"]
                          + precio_basico_2018 * m324) / precio_2018
        elif clave == "gas":
            precio_l_2018 = 10.0
            kg_por_mxn = (FISICOS["gas_lp"]["factor"] * 1.10) / precio_l_2018

        salida["categorias"][clave] = {
            "nombre": c["nombre"],
            "pregunta": c["pregunta"],
            "kg_co2e_por_mxn": round(kg_por_mxn, 5),
            "fisico": c.get("fisico"),
            "sectores_scian": (sorted(sel.index.tolist())
                               if c["sectores"] == "RESTO"
                               else c["sectores"]),
            "gasto_default_mxn_mes": round(default_mes, 0),
        }
        nom = c["nombre"][:34]
        print(f"{nom:36s} {kg_por_mxn*1000:7.1f} g/peso | "
              f"default {default_mes:8,.0f} MXN/mes | {len(sel)} sectores")

    out = ROOT / "web" / "intensidades_MEX.json"
    out.write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                   encoding="utf-8")

    # sanity: huella de la persona "promedio" usando los defaults
    tot = 0.0
    for clave, cat in salida["categorias"].items():
        gasto_2018 = cat["gasto_default_mxn_mes"] / INFLACION_2018_2026
        tot += gasto_2018 * 12 * cat["kg_co2e_por_mxn"]
    print(f"\n[sanity] persona promedio (defaults, vía IO): "
          f"{tot/1000:,.2f} t CO2e/año + directos (gasolina/gas ya en $ IO "
          f"aquí; en la web la parte física reemplaza al IO)")
    print(f"[ok] {out}")


if __name__ == "__main__":
    main()
