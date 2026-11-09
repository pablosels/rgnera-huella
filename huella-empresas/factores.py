# -*- coding: utf-8 -*-
"""Factores y tablas de clasificación de RGNERA Empresas.

Fuentes (verificadas el 28-oct-2026):
- Alimentos: Poore y Nemecek 2018, media mundial, vía Our World in Data
  (ourworldindata.org/grapher/ghg-per-kg-poore), kg CO2e por kg.
- Electricidad: factor del SEN 2024, 0.444 t CO2e/MWh (aviso SEMARNAT 28-feb-2025),
  vigente para 2026 (aviso de mayo de 2026).
- Combustibles: Acuerdo SEMARNAT, DOF 3-sep-2015 + Lista de combustibles CONUEE 2026,
  con PCG del AR5 (CH4 = 28, N2O = 265).
- Gasto: MIP 2018 del INEGI + inventario INECC (sectores_MEX_2018_mip.csv, motor de la
  calculadora de rgnera.com), deflactado con el INPC.
"""
import csv
import re
from pathlib import Path

AQUI = Path(__file__).resolve().parent

INPC_HOY_2018 = 146.075 / 99.909   # INPC sep-2026 (INEGI 619/26) / jul-2018
MARGEN_MAYOREO = 0.20              # parte del precio de un bien que es comercio (431)
PRECIO_KWH = 4.6                   # MXN/kWh sin IVA, PDBT aprox: solo si la factura no trae kWh

FISICOS = {   # kg CO2e por unidad física; precio sin IVA para estimar la cantidad si falta
    "electricidad": {"kg": 0.444, "unidad": "kWh", "precio": PRECIO_KWH},
    "gas_lp": {"kg": 1.650, "unidad": "L", "precio": 9.5},
    "gas_natural": {"kg": 1.884, "unidad": "m3", "precio": 13.0},
    "gasolina": {"kg": 2.546, "unidad": "L", "precio": 21.0},
    "diesel": {"kg": 2.73, "unidad": "L", "precio": 22.0},   # IPCC 2006, aprox
}

OWID = {"res": 99.48, "cordero": 39.72, "queso": 23.88, "cerdo": 12.31, "ave": 9.87,
        "pescado": 13.63, "camaron": 26.87, "huevo": 4.67, "leche": 3.15, "arroz": 4.45,
        "trigo": 1.57, "maiz": 1.70, "papa": 0.46, "jitomate": 2.09, "verdura": 0.53,
        "raiz": 0.43, "cebolla": 0.50, "citrico": 0.39, "platano": 0.86, "fruta": 1.05,
        "berries": 1.53, "manzana": 0.43, "azucar": 3.20, "cafe": 28.53, "chocolate": 46.65,
        "legumbre": 1.79, "nuez": 0.43, "cacahuate": 3.23, "avena": 2.48}

# Grupo de alimento por palabras de la descripción; el orden importa
# Grupo de alimento por palabras de la descripción; el orden importa: primero las especies
# que se nombran explícitamente (res, pescados) y al final las palabras genéricas de carne
# (filete, lomo, costilla, carne), para que "filete de salmón" no salga como res ni
# "costilla de res" como cerdo.
GRUPOS = [
    ("ave", r"\bpavo\b|pollo|pechuga|turkey|chicken|alitas?\b"),
    ("camaron", r"camar[oó]n|langostino"),
    ("pescado", r"salm[oó]n|at[uú]n|pescado|bacalao|caviar|robalo|huachinango|anchoa|tilapia|trucha|mojarra|sardina|pulpo|calamar|marisco"),
    ("res", r"\bres\b|arrachera|sirloin|rib ?eye|picaña|new york|t-?bone|brisket|chambarete|bistec|ternera"),
    ("cordero", r"cordero|borrego"),
    ("cerdo", r"cerdo|puerco|tocino|bacon|jam[oó]n|chorizo|salchich|pepperoni|prosciutto|serrano|lomo\b|costilla|chuleta|pancetta"),
    ("res", r"falda|molida|filete|hamburguesa|carne"),
    ("queso", r"queso|\bq\.|gouda|brie|parmesan|mozzarella|manchego|cheddar|feta|burrata|ricotta|mascarpone|camembert|cotija|panela|oaxaca|philadelphia"),
    ("huevo", r"huevo"),
    ("leche", r"leche|yogh?urt|crema\b|crema |nata|lyncott"),
    ("arroz", r"\barroz"),
    ("avena", r"avena"),
    ("maiz", r"tortilla|ma[ií]z|elote|tostada|masa"),
    ("trigo", r"harina|\bpan\b|baguette|brioche|bollo|pasta|spaghetti|fusilli|croissant|bagel|focaccia|bimbo"),
    ("jitomate", r"jitomate|tomate"),
    ("papa", r"\bpapas?\b|kletter|french fr"),
    ("raiz", r"camote|zanahoria|betabel|r[aá]bano|jengibre|yuca"),
    ("cebolla", r"cebolla|poro|ajo\b|cebollin"),
    ("citrico", r"lim[oó]n|toronja|naranja|mandarina|lima\b"),
    ("platano", r"pl[aá]tano"),
    ("berries", r"fresa|frutos rojos|zarzamora|frambuesa|mora\b|uva|ar[aá]ndano|berr"),
    ("manzana", r"manzana|pera\b"),
    ("fruta", r"aguacate|pi[ñn]a|mango|papaya|sand[ií]a|mel[oó]n|kiwi|guayaba|fruta|maracuy|coco|aceitun|durazno|ciruela|higo|xoconostle|tuna\b"),
    ("verdura", r"lechuga|espinaca|ar[uú]gula|kale|pepino|calabac|calabaza|pimiento|chile|br[oó]coli|coliflor|col\b|apio|champi|hongo|ejote|cilantro|perejil|albahaca|hierbabuena|menta|germinado|nopal|verdura|ensalada|jalape"),
    ("azucar", r"az[uú]car|piloncillo"),
    ("cafe", r"caf[eé]\b|espresso|grano de caf"),
    ("chocolate", r"chocolate|cacao|nutella"),
    ("legumbre", r"frijol?\b|garbanzo|lenteja|haba"),
    ("cacahuate", r"cacahuate|man[ií]\b"),
    ("nuez", r"nuez|almendra|pistache|avellana|macadamia|nueces"),
]
BEBIDA = re.compile(r"cerveza|\bvinos?\b|mezcal|tequila|whisk|wky|vodka|ginebra|\bgin\b|\bron\b|licor|vermouth|"
                    r"refresco|agua mineral|agua t[oó]nica|soda|jugo|kombucha|hielo|coca", re.I)

# ClaveProdServ del SAT (prefijo) -> subsector SCIAN de la MIP. Se usa el prefijo más largo.
SAT_SCIAN = {
    "10": "111", "11": "212", "12": "325", "13": "326", "14": "322", "15": "324",
    "20": "333", "21": "333", "22": "333", "23": "333", "24": "326", "25": "336", "26": "335",
    "27": "332", "30": "327", "31": "332", "32": "334", "39": "335", "40": "332", "41": "334",
    "42": "339", "43": "334", "44": "322", "45": "334", "46": "339", "47": "325", "48": "333",
    "49": "339", "50": "311", "5020": "312", "51": "325", "52": "335", "53": "315", "54": "339",
    "55": "323", "56": "337", "60": "339",
    "70": "115", "71": "213", "72": "238", "73": "561", "76": "561", "77": "562",
    "78": "484", "7811": "485", "7818": "811", "80": "541", "8013": "531", "8011": "561",
    "81": "541", "8111": "518", "82": "541", "83": "221", "8311": "517", "84": "522", "8411": "541", "8413": "524",
    "85": "621", "86": "611", "90": "722", "9011": "721", "9012": "561", "91": "812", "92": "561",
    "93": "813", "94": "813", "95": "531",
}
ETIQUETA_FISICO = {"gas_lp": "Gas LP", "gas_natural": "Gas natural",
                   "gasolina": "Gasolina y diésel (vehículos propios)", "diesel": "Gasolina y diésel (vehículos propios)"}
SERVICIO = {"E48", "ACT", "E51", "A9", "MON"}   # claves de unidad de servicio o actividad

# Algunos emisores usan mal la ClaveProdServ (p. ej. rentas facturadas como "restaurante",
# 90101501) o la de "no existe en el catálogo" (01010101): solo en esos casos la descripción
# manda sobre la clave.
CLAVE_DUDOSA = ("0101", "9010", "9011")
PRODUCTO_DESC = [
    (r"aceite|mantequilla|mayonesa|salsa|vinagre|especia|pimienta|paprika|consom|miel|mermelada|helado|panko|\bsal\b", "311"),
    (r"bolsa|vaso|tapa|contenedor|charola|popote|guante|playo|emplaye|cinta", "326"),
    (r"papel|servilleta|toalla|cart[oó]n|\bcaja", "322"),
    (r"cloro|jab[oó]n|detergente|limpiador|windex|desengrasante|fibra|esponja", "325"),
]
SERVICIO_DESC = [
    (r"renta de (equipo|lavaloza|terminal)|arrendamiento de equipo|alquiler de equipo", "532"),
    (r"\brenta\b|arrendamiento|alquiler", "531"),
    (r"comisi[oó]n|comisiones|dispersi[oó]n", "522"),
    (r"basura|recolecci[oó]n de residuos|residuos", "562"),
    (r"flete|env[ií]o|paqueter|mensajer", "492"),
    (r"mantenimiento|reparaci[oó]n|servicio t[eé]cnico", "811"),
    (r"limpieza|fumigaci", "561"),
    (r"seguridad|vigilancia", "561"),
    (r"software|licencia|sistema|\bapi|hosting|nube", "518"),
    (r"internet|telefon|telecom", "517"),
    (r"publicidad|marketing|dise[ñn]o|redes sociales|fotograf", "541"),
    (r"consultor|asesor|contab|honorario", "541"),
]
COMPRA_GRANDE = 0.10   # un concepto con más de este % del gasto se marca para revisar


def cargar_mip():
    with open(AQUI / "sectores_MEX_2018_mip.csv", encoding="utf-8-sig") as f:
        return {r["scian"]: (float(r["m_gCO2e_peso"]) / 1000, r["sector"]) for r in csv.DictReader(f)}


MIP = cargar_mip()


def kg_por_peso(scian, bien):
    """kg CO2e por peso de hoy sin IVA (precio comprador)."""
    m = MIP[scian][0]
    if bien:
        m = (1 - MARGEN_MAYOREO) * m + MARGEN_MAYOREO * MIP["431"][0]
    return m / INPC_HOY_2018


def grupo_alimento(texto):
    t = texto.lower()
    for g, rx in GRUPOS:
        if re.search(rx, t):
            return g
    return None


def sector_descripcion(texto, tabla=None):
    t = texto.lower()
    for rx, scian in (tabla or SERVICIO_DESC):
        if re.search(rx, t):
            return scian
    return None


def sector_concepto(clave, texto, bien):
    """Sector SCIAN de un concepto que no es comida ni combustible. None si no se sabe."""
    if clave.startswith(CLAVE_DUDOSA):
        return sector_descripcion(texto, PRODUCTO_DESC if bien else SERVICIO_DESC) or \
            sector_descripcion(texto, SERVICIO_DESC if bien else PRODUCTO_DESC) or \
            (None if clave.startswith("0101") else sector_sat(clave))
    return sector_sat(clave)


def sector_sat(clave):
    for n in (4, 2):
        s = SAT_SCIAN.get((clave or "")[:n])
        if s:
            return s
    return None
