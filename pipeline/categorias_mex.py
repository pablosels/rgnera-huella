# -*- coding: utf-8 -*-
"""
Mapeo de categorías de la calculadora -> subsectores SCIAN y generación de
web/intensidades_MEX.json.

- Intensidad de cada categoría = promedio de m (g CO2e/peso, Scope 3, MIP
  2018 + INEGyCEI) ponderado por el CONSUMO PRIVADO de cada subsector
  (columna CP de la propia MIP): pondera como realmente gastan los hogares.
- Gasto default por categoría = consumo privado per cápita mensual 2018 a
  PRECIO COMPRADOR (básico + márgenes de comercio y flete + impuestos netos,
  ver MARGEN_REL), escalado a pesos corrientes con un factor de inflación
  configurable.
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

# Defaults de luz y gas en PESOS DE HOY por persona al mes, desde datos físicos
# (antes ambos salían del consumo privado del SCIAN 221 = 284 MXN cada uno: luz +
# agua + gas por ductos a precios básicos, con subsidio; el gas LP ni está en el
# 221). Cuadran con la ENIGH 2024 (luz y combustibles ≈ 189 MXN/persona-mes de
# 2026, cuadro 15: 1,762 $/trimestre/hogar ÷ 3 ÷ 3.354; el resto es leña, carbón).
# Luz: CFE Suministro Básico 2023 (Tabla 30), doméstico 75,143 GWh ÷ ~130 M hab
# ÷ 12 ≈ 48 kWh → 50 kWh × 1.6 $/kWh (tarifa 1 a 147 kWh/mes con IVA) = 80.
# Gas: ~6.25 L LP-eq/persona-mes (Balance Nacional de Energía 2023 ≈ 6.2: 224.6 PJ
# LP + 26 PJ gas natural, 26.12 MJ/L; INEGyCEI 2024 1A4b ≈ 6.6) × 11.2 $/L = 70.
GASTO_LUZ_MES = 80.0
GASTO_GAS_MES = 70.0
# Gasolina, también física: los litros de los hogares que el puente de
# mexico_mip.py les asigna (supuesto A1: 40% de [1A3b] 170.8 Mt = 68.3 Mt ÷ 2.31
# kg/L = 29.6 GL ÷ 125.3 M ÷ 12 = 19.7 L/persona-mes) × 24 $/L = 472. Antes era
# el CP del 324 a precios básicos (446 = 18.6 L a 24 $/L): pasarlo a precio
# comprador daría ~30 L/mes y contaría la combustión de más (el 60% de [1A3b]
# ya va al 484, 485 y 487).
GASTO_GASOLINA_MES = 472.0

# Factores físicos de combustión directa (verificar en auditoría)
FISICOS = {
    "electricidad": {"factor": 0.444, "unidad": "kg CO2e por kWh",
                     "fuente": "Aviso FESEN 2024, CRE/SEMARNAT (0.444 "
                               "tCO2e/MWh)",
                     "precio_default_mxn": 1.6},   # = la web (tarifa 1)
    "gasolina": {"factor": 2.31, "unidad": "kg CO2 por litro",
                 "fuente": "IPCC 2006 gasolina automotriz",
                 "precio_default_mxn": 24.0},
    "gas_lp": {"factor": 1.66, "unidad": "kg CO2 por litro",
               "fuente": "IPCC 2006 GLP (2.98 kg/kg, densidad 0.54)",
               # CNE oct-2026: $20.73/kg (CDMX) × 0.54 kg/L ≈ 11.2 $/L
               "precio_default_mxn": 11.2},
    "vuelo": {"factor": 90.0, "unidad": "kg CO2e por hora de vuelo",
              "fuente": "Clase económica: ~0.11 kg CO2e/pasajero-km × "
                        "~800 km/h de crucero; coincide con DESNZ 2025 CON "
                        "efectos no-CO2 de altura (multiplicador 1.7); solo "
                        "CO2 serían ~55 kg/h",
              "precio_default_mxn": 1300.0},  # MXN por hora de vuelo aprox
    # Antes (hasta nov-2026) era un solo rubro "carne roja" a 21 kg CO2e/kg:
    # mezcla res/cerdo del consumo MX (~15 kg res, ~20 kg cerdo per cápita/
    # año), con modo $ a 170 MXN/kg. Se separó para que pasar de res a cerdo
    # se vea en el resultado.
    "res": {"factor": 40.0, "unidad": "kg CO2e por kg de carne de res",
            "fuente": "Bovino INECC 2018 (3A1+3B1 = 89 Mt, ~65% a carne) "
                      "÷ 1.98 Mt canal ÷ 0.75 rendimiento menudeo ≈ 39-40 "
                      "kg CO2e/kg; es un piso: sin alimento, potreros (3D1) ni "
                      "cambio de uso de suelo (UTCUTS); OWID: hato de carne "
                      "99.5, lechero 33.3",
            # Profeco 2026: promedio nacional de la res 164.85 MXN/kg (may),
            # bistec ~170-175; BM Editores ago-2026 ~174
            "precio_default_mxn": 170.0},
    "cerdo": {"factor": 6.5, "unidad": "kg CO2e por kg de carne de cerdo",
              "fuente": "Porcinos INECC 2018 (3A3+3B3 = 6.6 Mt) ÷ ~1.3-1.5 "
                        "Mt canal (SIAP, por verificar) ÷ 0.75 ≈ 6-7 kg "
                        "CO2e/kg; mismo límite que la res (piso); OWID 12.3",
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
# PENDIENTE (10-nov-2026), tres sesgos que van JUNTOS o no van: (1) los kilos
# de arranque de res y cerdo dan 49.4 kg CO2e/mes y la MIP les asigna 39.9 (lo
# que m_sin_res_cerdo le quita al súper): ×0.81 = res 0.82 y cerdo 1.08 kg,
# −9.5 kg/mes (verificar antes el balance SIAP de res 2018); (2) agua y drenaje
# sin rubro: +5.5 kg/mes (cadena de la rama 2213 + [5D1] municipal, que aquí
# cae en el 221 y se va con la luz física); (3) refrigerantes [2F]: el 30% de
# los hogares, +3.8 kg/mes. (2) y (3) como línea fija por persona, sin
# pregunta. Juntos: −0.2 kg/mes (el promedio sigue en 4.7 t); la carne sola lo
# bajaría a 4.6 y agua + refrigerantes solos lo subirían a 4.8.

# Clases SCIAN que separan rubros que comparten subsector. CP de la MIP 2018
# por clase (INEGI, data/mip2018/MIP_10.xlsx, columna CP), MMXN de 2018 a
# precios básicos.
# Taxis = rama 4853: 485311 de sitio 24,849 + 485312 de ruleteo 217,531 +
# 485320 alquiler de autos con chofer 138 (las apps no tienen clase en 2018).
# El resto del 485 (465,708) es transporte público: urbano 4851 = 159,311,
# foráneo 485210 = 288,896, escolar/personal y otros = 17,503.
CP_TAXIS_MMXN = 242_518
CP_485_MMXN = 708_226
# 325110 petroquímicos básicos (la EMIM pone ahí el gas licuado). Su CP no son
# medicinas: es combustible (gas LP, ya en 'gas' con factor físico) y quizá
# otro residuo del balance; se descuenta de farmacia y no se reasigna.
CP_325110_MMXN = 266_561
CP_325_MMXN = 556_877
# Pedidos a domicilio: gasto típico manual; sale del mismo CP del 722 que
# 'restaurantes', así que se le descuenta a ese rubro.
GASTO_APPS_COMIDA_MES = 200.0

# ---- Precio comprador ----
# La gente captura lo que paga; la MIP da el CP de cada bien a precios básicos y
# pone sus márgenes como CP de otros sectores: comercio (431 + 461 = 2,740,580
# MMXN) y flete (484 + 482 + 483 = 621,163), que caían en 'otros'. Los bienes
# que se capturan en pesos llevan aquí sus márgenes (con su m) y sus impuestos
# netos (sin emisiones), y esos márgenes salen de 'otros': ni se crea ni se
# pierde CO2e. (Antes: default a precio básico e intensidad diluida con
# MARGENES = {super .28, ropa .45, electrónica .40, hogar .40} a m461, que
# perdía f·CP·(m_bien − m461) ≈ 23 kg/persona-mes.)
COMERCIO, FLETE = ["431", "461"], ["484", "482", "483"]   # 486 (ductos) se queda
# Bienes que siguen fuera (sus márgenes se quedan en 'otros' o en el factor
# físico): CP básico MMXN y margen/valor básico (comercio, flete), 2018.
# Gasolina ~11 $/L básico: gasolinera ~1.3 + mayoreo ~0.6 $/L, pipa ~0.4. Gas LP:
# VPM ~6 vs ~10 $/L al público. Autos: agencia ~12%. Refacciones ~70%. Papel,
# pañales, plástico, llantas, ferretería, cemento: ~55% + flete pesado.
CP_AUTOS_MMXN = 399_233      # MIP_10: 336110 + motos, bicis y otros (336991-336999)
MARGEN_FUERA = {             # nombre: (sectores o CP, comercio, flete)
    "gasolina": (["324"], 0.18, 0.04),
    # el CP del 325110 (177 $ de 2018 por persona-mes a ~6 $/L básico ≈ 30 L) es
    # ~5 veces el gas LP físico de los hogares (6.25 L): si sobra margen aquí, falta
    # en los rubros (mueve el reparto, no el total)
    "gas_lp": (CP_325110_MMXN, 0.45, 0.05),
    "autos": (CP_AUTOS_MMXN, 0.12, 0.03),
    "autopartes": ("336-autos", 0.70, 0.05),
    "otros_bienes": (["113", "321", "322", "323", "326", "327", "331", "332",
                      "333"], 0.55, 0.08),
}
# Rubros: estructura relativa de los f anteriores (margen/básico =
# 1/((1−f)(1+IVA)) − 1, IVA 16% salvo súper) y flete por peso/valor; la escala
# la pone la MIP: los rubros se quedan con el resto de cada fondo (×1.69 el
# comercio, ×1.55 el flete). Sin COU 2018 por producto; afinable con ella.
MARGEN_REL = {"super": (0.389, 0.12), "ropa": (0.567, 0.03),
              "electronica": (0.437, 0.02), "hogar": (0.437, 0.06),
              "farmacia": (0.54, 0.04)}          # (margen total, flete)
# Impuestos netos sobre productos / valor antes de impuestos. IVA 16% en la parte
# gravada (comida y medicinas tasa 0; 312 sí) × 0.61 de cumplimiento efectivo, +
# IEPS 2018 (bebidas, tabaco, comida densa, telecom), ISH 3%; calibrado para que
# sumen los 951,517 MMXN de impuestos netos del CP (MIP_6, D.21−D.31). En los
# servicios solo cambia el default y el kg/peso, no el PERFIL. Educación, renta,
# transporte público y taxis: exentos.
IMPUESTO_NETO = {"super": 0.049, "ropa": 0.098, "electronica": 0.098,
                 "hogar": 0.098, "farmacia": 0.048, "restaurantes": 0.098,
                 "apps_comida": 0.098, "hoteles": 0.130, "telecom": 0.126,
                 "entretenimiento": 0.098, "personales": 0.098, "salud": 0.029,
                 "otros": 0.073}


def margenes_rubros(df, cp_rubro):
    """Márgenes de los rubros de bienes, MMXN por sector de margen:
    {rubro: {"431": .., "461": .., "484": .., "482": .., "483": ..}}."""
    cp = df["consumo_privado_MMXN"].clip(lower=0)
    fuera_c = fuera_f = 0.0
    for sect, c, f in MARGEN_FUERA.values():
        if sect == "336-autos":
            base = float(cp["336"]) - CP_AUTOS_MMXN
        elif isinstance(sect, list):
            base = float(cp[sect].sum())
        else:
            base = sect
        fuera_c += base * c
        fuera_f += base * f
    rel_c = {k: cp_rubro[k] * (mt - fl) for k, (mt, fl) in MARGEN_REL.items()}
    rel_f = {k: cp_rubro[k] * fl for k, (mt, fl) in MARGEN_REL.items()}
    kc = (cp[COMERCIO].sum() - fuera_c) / sum(rel_c.values())
    kf = (cp[FLETE].sum() - fuera_f) / sum(rel_f.values())
    assert kc > 0 and kf > 0, (kc, kf)
    out = {}
    for k in MARGEN_REL:
        d = {s: rel_c[k] * kc * cp[s] / cp[COMERCIO].sum() for s in COMERCIO}
        d.update({s: rel_f[k] * kf * cp[s] / cp[FLETE].sum() for s in FLETE})
        out[k] = d
    print(f"[márgenes] escala comercio ×{kc:.2f}, flete ×{kf:.2f}")
    return out


def cp_a_mes(cp_mmxn):
    """CP anual 2018 (MMXN) -> MXN de hoy por persona al mes."""
    return cp_mmxn * 1e6 / POB_2018 / 12 * INFLACION_2018_2026

CATEGORIAS = {
    "super": {
        "nombre": "Súper y comida en casa (sin res ni cerdo)",
        "pregunta": "¿Cuánto gastas al mes en súper, mercado y despensa, "
                    "sin contar la res ni el cerdo? (Jabón, detergente y "
                    "shampoo van en farmacia.)",
        "sectores": ["311", "312", "111", "112", "114"],
    },
    # Res y cerdo = lo que se COMPRA para comer en casa: su default sale del
    # súper (se le descuenta) y la carne de restaurantes y apps ya está en la
    # intensidad del 722 (~16% de ese rubro); preguntar "cuánto comes" la
    # contaría dos veces.
    "res": {
        "nombre": "Carne de res",
        "pregunta": "¿Cuántos kilos de res compras al mes para comer en "
                    "casa? Borrego y cabrito también van aquí; lo que comes "
                    "fuera ya cuenta en restaurantes y apps. (Cambia a $ si "
                    "no los sabes)",
        "sectores": ["112", "311"],
        "fisico": "res",
    },
    "cerdo": {
        "nombre": "Carne de cerdo",
        "pregunta": "¿Cuántos kilos de cerdo compras al mes para comer en "
                    "casa? Lo que comes fuera ya cuenta en restaurantes y "
                    "apps. (Cambia a $ si no los sabes)",
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
        "pregunta": "¿Cuánto pagas de luz al mes? El recibo de CFE suele ser "
                    "bimestral: divídelo entre 2 (igual los kWh).",
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
        "pregunta": "¿Cuánto gastas de gas al mes? (cilindro, estacionario o "
                    "natural)",
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
    # El 325 sin el 325110 es medicina Y limpieza y cuidado personal: CP 2018
    # por clase (MIP_10) 325412 farmacéutica 146,903 (51%), 325610 jabones,
    # detergentes y limpiadores 75,848 (26%), 325620 cosméticos y perfumes
    # 54,407 (19%), resto 4%. El default (567 a precio de tienda) incluye las
    # tres; la pregunta las nombra para que se capture lo mismo.
    "farmacia": {
        "nombre": "Farmacia, limpieza y cuidado personal",
        "pregunta": "¿Cuánto gastas al mes en medicinas y en artículos de "
                    "limpieza y cuidado personal (jabón, detergente, "
                    "shampoo, cosméticos)?",
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

    # márgenes de comercio y flete de los rubros de bienes (ver MARGEN_REL)
    cp_rubro = {k: float(df.loc[CATEGORIAS[k]["sectores"], "consumo_privado_MMXN"]
                         .clip(lower=0).sum()) for k in MARGEN_REL}
    cp_rubro["farmacia"] -= CP_325110_MMXN
    marg = margenes_rubros(df, cp_rubro)
    quitar = pd.Series(0.0, index=df.index)      # lo que sale de 'otros'
    for d in marg.values():
        for s, v in d.items():
            quitar[s] += v

    for clave, c in CATEGORIAS.items():
        if c["sectores"] == "RESTO":
            sel = df[~df.index.isin(cubiertos)]
        else:
            sel = df.loc[[s for s in c["sectores"] if s in df.index]]
        w = sel["consumo_privado_MMXN"].clip(lower=0)
        if c["sectores"] == "RESTO":
            # sin los márgenes que ya van con su bien (súper, ropa, etc.)
            assert set(quitar[quitar > 0].index) <= set(sel.index)
            w = w - quitar.reindex(w.index)
            assert (w >= 0).all(), w[w < 0]
        cp_total_mmxn = float(w.sum())
        if w.sum() <= 0:
            w = sel["x_MMXN"]
        col = ("m_sin_res_cerdo_gCO2e_peso" if clave == "super"
               else "m_gCO2e_peso")
        inten_g_peso = float((sel[col] * w).sum() / w.sum())
        if clave == "farmacia":
            assert abs(cp_total_mmxn - CP_325_MMXN) < 1, cp_total_mmxn
            cp_total_mmxn -= CP_325110_MMXN          # intensidad: la del 325
        if clave in marg:
            # Precio comprador = CP básico + márgenes (emiten con m431, m461,
            # m484...) + impuestos netos (no emiten). Las emisiones del rubro
            # quedan iguales a las de la MIP: m_bien·CP + Σ m_margen·margen.
            e_t = inten_g_peso * cp_total_mmxn + sum(
                v * float(df.loc[s, "m_gCO2e_peso"]) for s, v in marg[clave].items())
            cp_total_mmxn = ((cp_total_mmxn + sum(marg[clave].values()))
                             * (1 + IMPUESTO_NETO[clave]))
            inten_g_peso = e_t / cp_total_mmxn
        elif clave in IMPUESTO_NETO:
            # servicios y 'otros': + impuestos; mismas emisiones, más pesos
            cp_total_mmxn *= 1 + IMPUESTO_NETO[clave]
            inten_g_peso /= 1 + IMPUESTO_NETO[clave]
        default_mes = cp_a_mes(cp_total_mmxn)
        if clave == "super":
            # Res y cerdo van aparte con factor físico: fuera sus emisiones
            # (m_sin_res_cerdo, ver mexico_mip.py) Y su gasto (los 400 MXN que
            # se restan al default abajo). Intensidad del súper sin res ni
            # cerdo = (E − E_res_cerdo) / (CP − CP_res_cerdo). Quitar solo las
            # emisiones, sin este cociente, restaría la carne dos veces.
            inten_g_peso *= default_mes / (default_mes
                                           - GASTO_CARNE_ROJA_DESCUENTO_SUPER)
        elif clave in ("taxi_apps", "transporte_publico"):
            assert abs(cp_total_mmxn - CP_485_MMXN) < 1, cp_total_mmxn
            default_mes = cp_a_mes(CP_TAXIS_MMXN if clave == "taxi_apps"
                                   else CP_485_MMXN - CP_TAXIS_MMXN)
        elif clave == "restaurantes":
            # las apps de comida (default fijo abajo) son parte del mismo CP
            # del 722: restaurantes + apps = CP del 722, no CP + 200 (los dos
            # a precio comprador)
            default_mes -= GASTO_APPS_COMIDA_MES

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
            default_mes = GASTO_GASOLINA_MES   # físico, no el CP del 324
        elif clave == "gas":
            precio_l_2018 = 10.0
            kg_por_mxn = (FISICOS["gas_lp"]["factor"] * 1.10) / precio_l_2018
            default_mes = GASTO_GAS_MES        # físico, no el CP del 221
        if clave == "electricidad":
            default_mes = GASTO_LUZ_MES        # físico, no el CP del 221
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
            # (los 200 $ son precio comprador: sin impuestos para el kg/peso)
            kg_por_mxn = ((0.80 * m722 + 0.20 * m492)
                          / (1 + IMPUESTO_NETO["apps_comida"]))
            default_mes = GASTO_APPS_COMIDA_MES   # se le resta a 'restaurantes'

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
