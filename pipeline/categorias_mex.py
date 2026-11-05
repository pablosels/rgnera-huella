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
    "electricidad": {"factor": 0.444, "unidad": "kg CO2e por kWh",
                     "fuente": "Aviso FESEN 2024, CRE/SEMARNAT (0.444 "
                               "tCO2e/MWh)",
                     "precio_default_mxn": 1.8},
    "gasolina": {"factor": 2.31, "unidad": "kg CO2 por litro",
                 "fuente": "IPCC 2006 gasolina automotriz",
                 "precio_default_mxn": 24.0},
    "gas_lp": {"factor": 1.66, "unidad": "kg CO2 por litro",
               "fuente": "IPCC 2006 GLP (2.98 kg/kg, densidad 0.54)",
               "precio_default_mxn": 12.0},
    "vuelo": {"factor": 90.0, "unidad": "kg CO2e por hora de vuelo",
              "fuente": "Clase económica: ~0.11 kg CO2e/pasajero-km × "
                        "~800 km/h de crucero; solo combustión (sin efectos "
                        "no-CO2 de altura, que podrían duplicarlo)",
              "precio_default_mxn": 1300.0},  # MXN por hora de vuelo aprox
    # Antes (hasta nov-2026) era un solo rubro "carne roja" a 21 kg CO2e/kg:
    # mezcla res/cerdo del consumo MX (~15 kg res, ~20 kg cerdo per cápita/
    # año), con modo $ a 170 MXN/kg. Se separó para que pasar de res a cerdo
    # se vea en el resultado.
    "res": {"factor": 40.0, "unidad": "kg CO2e por kg de carne de res",
            "fuente": "Bovino INECC 2018 (3A1+3B1 = 89 Mt, ~65% a carne) "
                      "÷ 1.98 Mt canal ÷ 0.75 rendimiento menudeo ≈ 39-40 "
                      "kg CO2e/kg; extremo bajo frente a OWID (hato de carne "
                      "99.5, lechero 33.3)",
            # Profeco 2026: promedio nacional de la res 164.85 MXN/kg (may),
            # bistec ~170-175; BM Editores ago-2026 ~174
            "precio_default_mxn": 170.0},
    "cerdo": {"factor": 6.5, "unidad": "kg CO2e por kg de carne de cerdo",
              "fuente": "~6.5 kg CO2e/kg (valor del modelo de mezcla previo)",
              # Profeco jul-2026: pierna 98-126, chuleta 111-135 MXN/kg
              "precio_default_mxn": 120.0},
}

# Default de carne en KILOS: los mismos 2.35 kg/mes de res + cerdo del modelo
# de mezcla (400 MXN ÷ 170 MXN/kg), con la res en la proporción que da la
# mezcla de 21 kg CO2e/kg: (21 − 6.5) / (40 − 6.5) = 43% de los kilos (≈ los
# ~15 de ~35 kg per cápita al año). Así el perfil promedio no cambia:
# 1.02 kg × 40 + 1.33 kg × 6.5 = 49.4 kg CO2e/mes, igual que 2.35 × 21.
KG_CARNE_ROJA_MES = 400.0 / 170.0
PARTE_RES = (21.0 - 6.5) / (40.0 - 6.5)
# Lo que se descuenta del súper por la carne que se captura aparte: los mismos
# 400 MXN/mes de antes, para que el súper (y el perfil) no cambien. A precios
# de 2026 esos kilos cuestan ~333 MXN (173 + 160); la diferencia, 67 MXN de
# súper, serían ~2 kg CO2e/mes: dentro del error del modelo.
GASTO_CARNE_ROJA_DESCUENTO_SUPER = 400.0

CATEGORIAS = {
    "super": {
        "nombre": "Súper y comida en casa (sin res ni cerdo)",
        "pregunta": "¿Cuánto gastas al mes en súper, mercado y despensa, "
                    "sin contar la res ni el cerdo?",
        "sectores": ["311", "312", "111", "112", "114"],
    },
    "res": {
        "nombre": "Carne de res",
        "pregunta": "¿Cuántos kilos de res comes al mes? (borrego y cabrito "
                    "también van aquí; cambia a $ si no los sabes)",
        "sectores": ["112", "311"],
        "fisico": "res",
    },
    "cerdo": {
        "nombre": "Carne de cerdo",
        "pregunta": "¿Cuántos kilos de cerdo comes al mes? "
                    "(cambia a $ si no los sabes)",
        "sectores": ["112", "311"],
        "fisico": "cerdo",
    },
    "restaurantes": {
        "nombre": "Restaurantes, cafés y bares",
        "pregunta": "¿Cuánto gastas al mes en comer y beber fuera?",
        "sectores": ["722"],
    },
    "apps_comida": {
        "nombre": "Apps de comida (Uber Eats, DiDi Food, Rappi)",
        "pregunta": "¿Cuánto gastas al mes en pedidos a domicilio?",
        "sectores": ["722", "492"],
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
        "pregunta": "¿Cuántas horas de vuelo haces al año? (cada tramo "
                    "cuenta; puedes cambiar a $ si no las sabes)",
        "sectores": ["481"],
        "periodo": "anual",
        "fisico": "vuelo",
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
        "pregunta": "¿Cuánto gastas AL AÑO en muebles, electrodomésticos, hogar?",
        "sectores": ["337", "335", "339"],
        "periodo": "anual",
    },
    "salud": {
        "nombre": "Salud y médicos (sin farmacia)",
        "pregunta": "¿Cuánto gastas AL AÑO en médicos, dentista, hospital?",
        "sectores": ["621", "622", "623", "624"],
        "periodo": "anual",
    },
    "farmacia": {
        "nombre": "Farmacia y medicinas",
        "pregunta": "¿Cuánto gastas al mes en farmacia?",
        "sectores": ["325"],
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
        "pregunta": "¿Cuánto gastas AL AÑO en hospedaje y tours?",
        "sectores": ["721", "487"],
        "periodo": "anual",
    },
    "personales": {
        "nombre": "Servicios personales",
        "pregunta": "¿Cuánto gastas al mes en estética, tintorería, etc.?",
        "sectores": ["812"],
    },
    "otros": {
        "nombre": "Otros gastos",
        "pregunta": "Auto o moto (compra y mantenimiento), bancos y seguros, "
                    "envíos y paquetería, trabajadores del hogar, cuotas y "
                    "donativos, regalos, papelería y demás compras del mes",
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

        # Bienes al menudeo: el usuario paga precio comprador (margen de
        # comercio + IVA) pero m está a precios básicos del productor.
        # Mezcla: (1-f)·m_producto + f·m_comercio_menudeo, con f aprox.
        # de márgenes COU + IVA (afinable con la COU de INEGI).
        MARGENES = {"super": 0.28, "ropa": 0.45,
                    "electronica": 0.40, "hogar": 0.40}
        if clave in MARGENES:
            f = MARGENES[clave]
            m461 = float(df.loc["461", "m_gCO2e_peso"]) / 1000
            kg_por_mxn = (1 - f) * kg_por_mxn + f * m461

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
        elif clave in ("res", "cerdo"):
            # Bottom-up del propio inventario INECC 2018:
            #  res: bovino 3A1+3B1 = 89 Mt, ~65% asignado a carne (vs leche)
            #       ÷ 1.98 Mt canal ÷ 0.75 rendimiento menudeo ≈ 39 kg CO2e/kg
            #  cerdo: ~6.5 kg CO2e/kg
            # (antes, mezcla de gasto res/cerdo ~55/45 => 0.17 kg CO2e/MXN de
            # 2018). En la web manda el factor físico; aquí kg/MXN de 2018 se
            # deja consistente con él: factor ÷ (precio 2026 ÷ inflación).
            fis = FISICOS[clave]
            kg_por_mxn = (fis["factor"] * INFLACION_2018_2026
                          / fis["precio_default_mxn"])
            kilos = KG_CARNE_ROJA_MES * (PARTE_RES if clave == "res"
                                         else 1 - PARTE_RES)
            default_mes = kilos * fis["precio_default_mxn"]
        elif clave == "apps_comida":
            # pedido a domicilio ≈ 80% preparación de alimentos (722) +
            # 20% logística de entrega (492 mensajería)
            m722 = float(df.loc["722", "m_gCO2e_peso"]) / 1000
            m492 = float(df.loc["492", "m_gCO2e_peso"]) / 1000
            kg_por_mxn = 0.80 * m722 + 0.20 * m492
            default_mes = 200.0   # gasto típico manual; CP de 722 ya está
                                  # contado en 'restaurantes'

        periodo = c.get("periodo", "mensual")
        salida["categorias"][clave] = {
            "nombre": c["nombre"],
            "pregunta": c["pregunta"],
            "kg_co2e_por_mxn": round(kg_por_mxn, 5),
            "fisico": c.get("fisico"),
            "periodo": periodo,
            "sectores_scian": (sorted(sel.index.tolist())
                               if c["sectores"] == "RESTO"
                               else c["sectores"]),
            # el default se expresa en el periodo de captura
            "gasto_default_mxn": round(default_mes * (12 if periodo == "anual"
                                                      else 1), 0),
        }
        nom = c["nombre"][:34]
        print(f"{nom:36s} {kg_por_mxn*1000:7.1f} g/peso | "
              f"default {default_mes:8,.0f} MXN/mes | {len(sel)} sectores")

    # la res y el cerdo se capturan aparte: se descuentan del default del súper
    salida["categorias"]["super"]["gasto_default_mxn"] -= \
        GASTO_CARNE_ROJA_DESCUENTO_SUPER

    out = ROOT / "web" / "intensidades_MEX.json"
    out.write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                   encoding="utf-8")

    # sanity: huella de la persona "promedio" usando los defaults
    tot = 0.0
    for clave, cat in salida["categorias"].items():
        mens = cat["gasto_default_mxn"] / (12 if cat["periodo"] == "anual" else 1)
        tot += mens / INFLACION_2018_2026 * 12 * cat["kg_co2e_por_mxn"]
    print(f"\n[sanity] persona promedio (defaults, vía IO): "
          f"{tot/1000:,.2f} t CO2e/año + directos (gasolina/gas ya en $ IO "
          f"aquí; en la web la parte física reemplaza al IO)")
    print(f"[ok] {out}")


if __name__ == "__main__":
    main()
