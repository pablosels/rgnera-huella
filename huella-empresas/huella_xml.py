# -*- coding: utf-8 -*-
"""Huella de carbono de una empresa a partir de los XML de sus CFDI (RGNERA Empresas).

Lee carpetas o .zip con los XML que bajó el cliente del portal del SAT, se queda con
las facturas que RECIBIÓ (su RFC como receptor), clasifica cada concepto y escribe un
Excel con el resumen por alcance, el detalle por concepto y lo que hay que revisar a mano.

  Alcance 1: gas LP, gas natural y combustibles, por litro o m3 (si la factura no trae
             la cantidad, se estima con el precio).
  Alcance 2: electricidad por kWh (los CFDI de CFE traen los kWh).
  Alcance 3: alimentos por kilo (Poore y Nemecek 2018); si no hay kilos, se estiman con el
             precio mediano por kilo de ese grupo en las propias compras; lo demás por
             pesos con la MIP 2018 del INEGI + INECC según su ClaveProdServ.

Uso:
  python huella_xml.py <carpeta_o_zip> [...] --rfc RFC_DEL_CLIENTE --salida reporte.xlsx
         [--desde 2026-01-01] [--hasta 2026-12-31] [--anualizar] [--ventas 2500000]
         [--extra sin_factura.json]

sin_factura.json (compras sin CFDI), una lista de renglones como:
  {"concepto": "Pollo de un proveedor sin factura", "grupo": "ave", "kg": 200}
  {"concepto": "Recibo de luz sin XML", "kwh": 800}
  {"concepto": "Gas LP en efectivo", "fisico": "gas_lp", "cantidad": 300}
  {"concepto": "Recolección de basura", "scian": "562", "pesos": 2000}
"""
import argparse
import io
import json
import statistics
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

import factores as F

sys.stdout.reconfigure(encoding="utf-8")

CFE_RFC = {"CFE370814QI0", "CSS160330CP7"}   # CFE y CFE Suministrador de Servicios Básicos
UNIDAD_KG = {"KGM": 1.0, "GRM": 0.001}
UNIDAD_L = {"LTR": 1.0, "MLT": 0.001, "HLT": 100.0}
GRUPO_ETIQUETA = {"res": "res", "cerdo": "cerdo", "ave": "pollo y pavo", "queso": "queso",
                  "leche": "leche y crema", "huevo": "huevo", "pescado": "pescados y mariscos",
                  "camaron": "pescados y mariscos", "cordero": "cordero"}


# ---------------------------------------------------------------- lectura
def xml_de(rutas):
    """Devuelve (nombre, bytes) de cada XML en las carpetas o zips dados."""
    for r in map(Path, rutas):
        if r.is_dir():
            for p in r.rglob("*"):
                if p.suffix.lower() == ".xml":
                    yield str(p), p.read_bytes()
                elif p.suffix.lower() == ".zip":
                    yield from xml_de([p])
        elif r.suffix.lower() == ".zip":
            with zipfile.ZipFile(r) as z:
                for n in z.namelist():
                    if n.lower().endswith(".xml"):
                        yield f"{r}!{n}", z.read(n)
        elif r.suffix.lower() == ".xml":
            yield str(r), r.read_bytes()


def leer_cfdis(rutas, rfc, desde, hasta):
    vistos, cfdis, descartes = set(), [], defaultdict(int)
    for nombre, datos in xml_de(rutas):
        try:
            raiz = ET.parse(io.BytesIO(datos)).getroot()
        except ET.ParseError:
            descartes["XML ilegible"] += 1
            continue
        if not raiz.tag.endswith("Comprobante"):
            continue
        ns = raiz.tag[1:].split("}")[0]
        q = lambda t: f"{{{ns}}}{t}"
        uuid = next((e.get("UUID") for e in raiz.iter() if e.tag.endswith("TimbreFiscalDigital")), nombre)
        if uuid in vistos:
            descartes["duplicado"] += 1
            continue
        vistos.add(uuid)
        tipo = raiz.get("TipoDeComprobante", "I")
        if tipo in ("P", "N", "T"):
            descartes[{"P": "complemento de pago", "N": "nómina", "T": "traslado"}[tipo]] += 1
            continue
        emi, rec = raiz.find(q("Emisor")), raiz.find(q("Receptor"))
        if rfc and (rec is None or rec.get("Rfc", "").upper() != rfc.upper()):
            descartes["no es compra del cliente"] += 1
            continue
        fecha = (raiz.get("Fecha") or "")[:10]
        if (desde and fecha < desde) or (hasta and fecha > hasta):
            descartes["fuera del periodo"] += 1
            continue
        tc = float(raiz.get("TipoCambio") or 1) if raiz.get("Moneda", "MXN") not in ("MXN", "XXX") else 1.0
        signo = -1 if tipo == "E" else 1
        conceptos = []
        for c in raiz.iter(q("Concepto")):
            monto = (float(c.get("Importe") or 0) - float(c.get("Descuento") or 0)) * tc * signo
            conceptos.append({"clave": c.get("ClaveProdServ", ""), "unidad": (c.get("ClaveUnidad") or "").upper(),
                              "cantidad": float(c.get("Cantidad") or 0) * signo,
                              "descripcion": " ".join((c.get("Descripcion") or "").split()), "monto": monto})
        cfdis.append({"uuid": uuid, "fecha": fecha, "emisor_rfc": emi.get("Rfc", "") if emi is not None else "",
                      "emisor": emi.get("Nombre", "") if emi is not None else "", "conceptos": conceptos})
    return cfdis, descartes


# ---------------------------------------------------------------- clasificación
def combustible(desc, clave=""):
    """Tipo de combustible por la descripción; si no dice, por la clave del SAT
    (1510 = combustibles de petróleo: gasolina; 1511 = gaseosos: gas LP)."""
    d = desc.lower()
    if "natural" in d:
        return "gas_natural"
    if "diesel" in d or "diésel" in d:
        return "diesel"
    if any(k in d for k in ("gasolina", "magna", "premium")):
        return "gasolina"
    if any(k in d for k in ("gas lp", "gas l.p", "l.p.", "propano", "butano")):
        return "gas_lp"
    return "gasolina" if clave.startswith("1510") else "gas_lp"


def fisico(tipo, cantidad, unidad, monto):
    """kg CO2e de un combustible o de electricidad, por cantidad si la hay, si no por precio."""
    f = F.FISICOS[tipo]
    # CFE suele timbrar "Energía" con Cantidad 1 KWH y todo el cargo en el importe: solo se
    # creen los kWh si el precio unitario que resulta es razonable
    if tipo == "electricidad" and unidad == "KWH" and cantidad > 0 and monto / cantidad <= 15:
        q, metodo = cantidad, "kWh de la factura"
    elif tipo in ("gas_lp", "gasolina", "diesel") and unidad in UNIDAD_L:
        q, metodo = cantidad * UNIDAD_L[unidad], "litros de la factura"
    elif tipo == "gas_lp" and unidad in UNIDAD_KG:
        q, metodo = cantidad * UNIDAD_KG[unidad] / 0.54, "kilos de la factura"
    elif tipo == "gas_natural" and unidad == "MTQ":
        q, metodo = cantidad, "m3 de la factura"
    else:
        q, metodo = monto / f["precio"], f"estimado con ${f['precio']}/{f['unidad']}"
    return q * f["kg"], q, f["unidad"], metodo


def clasificar(cfdis):
    """Devuelve una lista de renglones (un concepto cada uno) con su categoría y kg CO2e."""
    # precio mediano por kilo de cada grupo de alimento, con las propias compras en kilos
    precios = defaultdict(list)
    for cf in cfdis:
        for c in cf["conceptos"]:
            g = F.grupo_alimento(c["descripcion"])
            if g and c["unidad"] in UNIDAD_KG and c["cantidad"] > 0:
                precios[g].append(c["monto"] / (c["cantidad"] * UNIDAD_KG[c["unidad"]]))
    p_kg = {g: statistics.median(v) for g, v in precios.items()}

    filas = []
    for cf in cfdis:
        es_cfe = cf["emisor_rfc"].upper() in CFE_RFC or "comision federal de electricidad" in cf["emisor"].lower()
        hay_kwh = any(c["unidad"] == "KWH" for c in cf["conceptos"])
        if es_cfe and not hay_kwh:      # sin kWh: un solo estimado con el total de la factura
            total = sum(c["monto"] for c in cf["conceptos"])
            cf["conceptos"] = [{"clave": "83101801", "unidad": "", "cantidad": 0,
                                "descripcion": "Electricidad (total del recibo, sin kWh)", "monto": total}]
        for c in cf["conceptos"]:
            r = dict(c, fecha=cf["fecha"], uuid=cf["uuid"], emisor=cf["emisor"], revisar="")
            clave, desc, u = c["clave"], c["descripcion"], c["unidad"]
            g = F.grupo_alimento(desc)
            if clave.startswith("831018") or u == "KWH" or es_cfe:
                if es_cfe and hay_kwh and u != "KWH":
                    r.update(categoria="Alcance 2 · Electricidad", alcance=2, kg=0.0,
                             metodo="cargo del recibo (sin emisiones extra)", cant_fis=0, u_fis="")
                else:
                    kg, q, uf, m = fisico("electricidad", c["cantidad"], u, c["monto"])
                    r.update(categoria="Alcance 2 · Electricidad", alcance=2, kg=kg, metodo=m, cant_fis=q, u_fis=uf)
            elif clave.startswith(("1511", "1510", "831016")):
                t = "gas_natural" if clave.startswith("831016") else combustible(desc, clave)
                kg, q, uf, m = fisico(t, c["cantidad"], u, c["monto"])
                r.update(categoria=f"Alcance 1 · {F.ETIQUETA_FISICO[t]}", alcance=1, kg=kg, metodo=m, cant_fis=q, u_fis=uf)
            elif clave.startswith("5020") or (F.BEBIDA.search(desc) and (clave.startswith("50") or clave.startswith("0101"))):
                r.update(categoria="Alcance 3 · Bebidas", alcance=3, kg=c["monto"] * F.kg_por_peso("312", True),
                         metodo="pesos × MIP (312)", cant_fis=0, u_fis="")
            elif g and (clave.startswith("50") or clave.startswith("0101")):
                etq = "Alcance 3 · Alimentos: " + GRUPO_ETIQUETA.get(
                    g, "granos y panadería" if g in ("trigo", "maiz", "arroz", "avena") else "verduras, frutas y otros")
                if u in UNIDAD_KG:
                    kg_al, m = c["cantidad"] * UNIDAD_KG[u], "kilos de la factura"
                elif g == "leche" and u in UNIDAD_L:
                    kg_al, m = c["cantidad"] * UNIDAD_L[u] * 1.03, "litros de la factura"
                elif g in p_kg:
                    kg_al, m = c["monto"] / p_kg[g], f"kilos estimados a ${p_kg[g]:,.0f}/kg"
                else:
                    kg_al, m = None, None
                if kg_al is not None:
                    r.update(categoria=etq, alcance=3, kg=kg_al * F.OWID[g], metodo=m, cant_fis=kg_al, u_fis="kg")
                else:
                    r.update(categoria=etq, alcance=3, kg=c["monto"] * F.kg_por_peso("311", True),
                             metodo="pesos × MIP (311): sin precio por kilo de referencia", cant_fis=0, u_fis="")
            else:
                bien = u not in F.SERVICIO and clave[:2] < "70"
                scian = F.sector_concepto(clave, desc, bien)
                if scian is None:
                    scian = "541" if not bien else "461"
                    r["revisar"] = "ClaveProdServ sin catálogo: confirma qué es"
                cat = "Alcance 3 · Alimentos: otros" if scian == "311" else f"Alcance 3 · {F.MIP[scian][1][:60]}"
                r.update(categoria=cat, alcance=3, kg=c["monto"] * F.kg_por_peso(scian, bien),
                         metodo=f"pesos × MIP ({scian})", cant_fis=0, u_fis="")
            filas.append(r)
    gasto = sum(f["monto"] for f in filas) or 1
    for f in filas:
        if (f["monto"] > F.COMPRA_GRANDE * gasto and not f["revisar"] and f["alcance"] == 3
                and "(531)" not in f["metodo"]):
            f["revisar"] = (f"Concepto grande ({f['monto'] / gasto:.0%} del gasto): confirma su sector; si es "
                            "equipo o una obra que no se repite, va en la categoría 2 (bienes de capital)")
    return filas


def extras(ruta):
    filas = []
    for e in json.loads(Path(ruta).read_text(encoding="utf-8")):
        r = {"fecha": "", "uuid": "sin factura", "emisor": "sin factura", "clave": "", "unidad": "",
             "cantidad": 0, "descripcion": e.get("concepto", ""), "monto": e.get("pesos", 0.0), "revisar": ""}
        if "kg" in e and e.get("grupo") in F.OWID:
            r.update(categoria="Alcance 3 · Alimentos: " + GRUPO_ETIQUETA.get(e["grupo"], e["grupo"]), alcance=3,
                     kg=e["kg"] * F.OWID[e["grupo"]], metodo="kilos declarados", cant_fis=e["kg"], u_fis="kg")
        elif "kwh" in e:
            r.update(categoria="Alcance 2 · Electricidad", alcance=2, kg=e["kwh"] * F.FISICOS["electricidad"]["kg"],
                     metodo="kWh declarados", cant_fis=e["kwh"], u_fis="kWh")
        elif e.get("fisico") in F.FISICOS:
            t = e["fisico"]
            r.update(categoria=f"Alcance 1 · {F.ETIQUETA_FISICO[t]}", alcance=1, kg=e["cantidad"] * F.FISICOS[t]["kg"],
                     metodo="cantidad declarada", cant_fis=e["cantidad"], u_fis=F.FISICOS[t]["unidad"])
        elif e.get("scian") in F.MIP:
            r.update(categoria=f"Alcance 3 · {F.MIP[e['scian']][1][:60]}", alcance=3,
                     kg=e["pesos"] * F.kg_por_peso(e["scian"], False), metodo=f"pesos declarados × MIP ({e['scian']})",
                     cant_fis=0, u_fis="")
        else:
            raise SystemExit(f"Renglón de --extra sin datos suficientes: {e}")
        filas.append(r)
    return filas


# ---------------------------------------------------------------- reporte
def escribir_excel(salida, filas, resumen, supuestos):
    wb = Workbook()
    neg, cab = Font(bold=True), PatternFill("solid", fgColor="E3DCCB")

    def hoja(titulo, columnas, renglones, primera=False):
        ws = wb.active if primera else wb.create_sheet()
        ws.title = titulo
        ws.append(columnas)
        for celda in ws[1]:
            celda.font, celda.fill = neg, cab
        for r in renglones:
            ws.append(r)
        for i, col in enumerate(columnas, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = max(12, min(60, len(str(col)) + 4))
        return ws

    hoja("Resumen", ["Concepto", "Valor"], resumen, primera=True).column_dimensions["A"].width = 46
    cats = defaultdict(lambda: [0.0, 0.0, set()])
    for f in filas:
        a = cats[f["categoria"]]; a[0] += f["monto"]; a[1] += f["kg"]; a[2].add(f["metodo"].split(":")[0])
    total = sum(v[1] for v in cats.values()) or 1
    hoja("Por categoría", ["Categoría", "Gasto sin IVA (MXN)", "t CO2e", "% del total", "Método"],
         [[k, round(v[0], 2), round(v[1] / 1000, 3), round(v[1] / total * 100, 1), " / ".join(sorted(v[2]))[:120]]
          for k, v in sorted(cats.items(), key=lambda x: -x[1][1])])
    cols = ["Fecha", "UUID", "Emisor", "ClaveProdServ", "Descripción", "Cantidad", "Unidad", "Monto sin IVA",
            "Categoría", "Método", "Cantidad física", "Unidad física", "kg CO2e", "Revisar"]
    det = [[f["fecha"], f["uuid"], f["emisor"], f["clave"], f["descripcion"], f["cantidad"], f["unidad"],
            round(f["monto"], 2), f["categoria"], f["metodo"], round(f["cant_fis"], 2), f["u_fis"],
            round(f["kg"], 2), f["revisar"]] for f in filas]
    hoja("Detalle", cols, det)
    hoja("Por revisar", cols, [d for d, f in zip(det, filas) if f["revisar"] or "estimado" in f["metodo"]])
    hoja("Supuestos", ["Supuesto"], [[s] for s in supuestos]).column_dimensions["A"].width = 120
    wb.save(salida)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rutas", nargs="+")
    ap.add_argument("--rfc", required=True, help="RFC del cliente (receptor de las facturas)")
    ap.add_argument("--salida", default="huella.xlsx")
    ap.add_argument("--desde"), ap.add_argument("--hasta")
    ap.add_argument("--anualizar", action="store_true", help="escala el periodo a 12 meses")
    ap.add_argument("--ventas", type=float, help="ventas anuales sin IVA, para kg CO2e por $1,000")
    ap.add_argument("--extra", help="JSON con compras sin factura")
    a = ap.parse_args()

    cfdis, descartes = leer_cfdis(a.rutas, a.rfc, a.desde, a.hasta)
    if not cfdis:
        raise SystemExit(f"No hay facturas recibidas por {a.rfc} en esas rutas. Descartes: {dict(descartes)}")
    filas = clasificar(cfdis) + (extras(a.extra) if a.extra else [])
    fechas = sorted(f["fecha"] for f in filas if f["fecha"])
    d0, d1 = date.fromisoformat(a.desde or fechas[0]), date.fromisoformat(a.hasta or fechas[-1])
    dias = (d1 - d0).days + 1
    escala = 365 / dias if a.anualizar else 1.0
    for f in filas:
        f["kg"] *= escala; f["monto"] *= escala; f["cant_fis"] *= escala

    t = {k: sum(f["kg"] for f in filas if f["alcance"] == k) / 1000 for k in (1, 2, 3)}
    tot = sum(t.values())
    resumen = [["RFC del cliente", a.rfc.upper()], ["Periodo de las facturas", f"{d0} a {d1} ({dias} días)"],
               ["Anualizado", "sí, × %.2f" % escala if a.anualizar else "no"],
               ["Facturas leídas", len(cfdis)], ["Conceptos clasificados", len(filas)],
               ["Gasto analizado sin IVA (MXN)", round(sum(f["monto"] for f in filas), 2)],
               ["Alcance 1 (t CO2e)", round(t[1], 2)], ["Alcance 2 (t CO2e)", round(t[2], 2)],
               ["Alcance 3 (t CO2e)", round(t[3], 2)], ["TOTAL (t CO2e)", round(tot, 2)],
               ["Conceptos por revisar", sum(1 for f in filas if f["revisar"] or "estimado" in f["metodo"])]]
    if a.ventas:
        resumen.append(["kg CO2e por cada $1,000 de venta", round(tot * 1e6 / a.ventas, 1)])
    resumen += [[f"Descartado: {k}", v] for k, v in descartes.items()]
    supuestos = [
        "Alcance 3 por gasto: MIP 2018 del INEGI + inventario INECC; pesos deflactados con INPC "
        f"sep-2026/jul-2018 = {F.INPC_HOY_2018:.4f}; a los bienes se les quita {F.MARGEN_MAYOREO:.0%} de margen comercial.",
        "Alimentos por kilo: Poore y Nemecek 2018, media mundial (Our World in Data). La res usa ganado de carne (99.48 kg/kg).",
        "Electricidad: 0.444 kg CO2e/kWh (factor SEN 2024, vigente 2026). Sin kWh en la factura se estima a "
        f"${F.PRECIO_KWH}/kWh.",
        "Combustibles: DOF 3-sep-2015 + CONUEE 2026 (gas LP 1.650 kg/L, gas natural 1.884 kg/m3, gasolina 2.546 kg/L).",
        "No incluye: traslados del personal, viajes de clientes, ni compras sin CFDI salvo las de --extra.",
    ]
    escribir_excel(a.salida, filas, resumen, supuestos)
    print(f"{a.rfc}: {tot:,.1f} t CO2e (A1 {t[1]:,.1f} · A2 {t[2]:,.1f} · A3 {t[3]:,.1f})"
          f"{' anualizado' if a.anualizar else ''} · {len(cfdis)} facturas · {dias} días")
    cats = defaultdict(float)
    for f in filas:
        cats[f["categoria"]] += f["kg"] / 1000
    for k, v in sorted(cats.items(), key=lambda x: -x[1])[:8]:
        print(f"  {v:8.2f} t  {k}")
    print(f"  descartes: {dict(descartes)}")
    print(f"OK: {a.salida}")


if __name__ == "__main__":
    main()
