# -*- coding: utf-8 -*-
"""Genera CFDI 4.0 sintéticos (cliente ROS190101AB1) para probar huella_xml.py.

Cubre: CFE con "1 KWH" y el cargo en el importe, CFE con kWh reales, CFE sin kWh, gas LP en
litros y en kilos, gasolina/diésel/"COMBUSTIBLE", gas natural en m3, alimentos por kilo y por
pieza, bebidas, nota de crédito, claves 01010101 y 90101501, descuento, factura en USD, y los
descartes (pago, nómina, emitida por el cliente, duplicada, fuera de periodo, XML ilegible, zip).

Uso (desde huella-empresas):
  python pruebas/gen_cfdi.py pruebas/cfdi
  python huella_xml.py pruebas/cfdi --rfc ROS190101AB1 --desde 2026-07-01 --hasta 2026-09-30 --extra sin_factura_ejemplo.json --salida pruebas/prueba.xlsx
Valores esperados en el Detalle: salmón 5 kg = 68.15 kg CO2e, costilla de res 4 kg = 397.92,
COMBUSTIBLE 10 L = 25.46 (gasolina), gas natural 150 m3 = 282.6, Energía "1 KWH" $4,600 = 1,000 kWh = 444.
"""
import sys, zipfile
from pathlib import Path
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
CLI = "ROS190101AB1"   # el cliente
n = [0]
def cfdi(emisor_rfc, emisor, conceptos, tipo="I", fecha="2026-08-15T10:00:00", receptor=CLI,
         moneda="MXN", tc=None, uuid=None, nombre=None):
    n[0] += 1
    uuid = uuid or f"00000000-0000-0000-0000-{n[0]:012d}"
    cs = ""
    for c in conceptos:
        clave, desc, cant, uni, imp = c[:5]
        desc_ = f' Descuento="{c[5]}"' if len(c) > 5 else ""
        cs += (f'<cfdi:Concepto ClaveProdServ="{clave}" Cantidad="{cant}" ClaveUnidad="{uni}" '
               f'Descripcion="{desc}" ValorUnitario="{imp/cant if cant else imp}" Importe="{imp}"{desc_} ObjetoImp="02"/>')
    tcx = f' TipoCambio="{tc}"' if tc else ""
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
           f'xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" Version="4.0" Fecha="{fecha}" '
           f'TipoDeComprobante="{tipo}" Moneda="{moneda}"{tcx} SubTotal="0" Total="0">'
           f'<cfdi:Emisor Rfc="{emisor_rfc}" Nombre="{emisor}" RegimenFiscal="601"/>'
           f'<cfdi:Receptor Rfc="{receptor}" Nombre="CLIENTE" UsoCFDI="G03"/>'
           f'<cfdi:Conceptos>{cs}</cfdi:Conceptos>'
           f'<cfdi:Complemento><tfd:TimbreFiscalDigital Version="1.1" UUID="{uuid}"/></cfdi:Complemento>'
           f'</cfdi:Comprobante>')
    (out / (nombre or f"{n[0]:02d}.xml")).write_text(xml, encoding="utf-8")

# A: CFE con "1 KWH" y todo el cargo en el importe (debe estimarse por precio) + DAP sin kWh
cfdi("CSS160330CP7", "CFE SUMINISTRADOR DE SERVICIOS BASICOS",
     [("83101801", "Energía", 1, "KWH", 4600.0), ("83101800", "DAP alumbrado", 1, "E48", 120.0)])
# B: CFE con kWh reales
cfdi("CSS160330CP7", "CFE SUMINISTRADOR DE SERVICIOS BASICOS", [("83101801", "Energía", 2400, "KWH", 7680.0)])
# C: CFE sin ningún KWH (recibo viejo): un solo estimado con el total
cfdi("CFE370814QI0", "COMISION FEDERAL DE ELECTRICIDAD", [("83101800", "Suministro", 1, "E48", 2300.0), ("83101800", "Cargo fijo", 1, "E48", 100.0)])
# D: gas LP en litros
cfdi("FGA900101XX1", "FLAMA GAS", [("15111509", "GAS LP", 300, "LTR", 2850.0)])
# E: gas LP en kilos
cfdi("FGA900101XX1", "FLAMA GAS", [("15111509", "GAS L.P. CILINDRO", 100, "KGM", 1750.0)])
# F: gasolina con palabra clave, diésel, y "COMBUSTIBLE" sin palabra clave con clave de gasolina
cfdi("PEM000101XX1", "GASOLINERA", [("15101514", "GASOLINA MAGNA", 50, "LTR", 1050.0),
                                    ("15101505", "DIESEL", 20, "LTR", 440.0),
                                    ("15101514", "COMBUSTIBLE", 10, "LTR", 210.0)])
# G: alimentos
cfdi("CAR000101XX1", "CARNES FINAS", [("50111513", "ARRACHERA DE RES", 10, "KGM", 2800.0),
                                      ("50121537", "FILETE DE SALMON FRESCO", 5, "KGM", 1750.0),
                                      ("50121538", "LOMO DE ATUN", 2, "KGM", 600.0),
                                      ("50111513", "COSTILLA DE RES", 4, "KGM", 800.0),
                                      ("50112004", "PECHUGA DE POLLO", 20, "KGM", 1600.0),
                                      ("50112004", "PECHUGA DE POLLO EMPACADA", 4, "H87", 480.0),   # 4 piezas: estimar con $80/kg -> 6 kg
                                      ("50131700", "QUESO MANCHEGO", 3, "KGM", 540.0),
                                      ("50131701", "LECHE ENTERA", 10, "LTR", 250.0),
                                      ("50192100", "FRESAS", 2, "KGM", 160.0)])
# H: bebidas y un "turrón" (ron)
cfdi("BEB000101XX1", "BEBIDAS", [("50202201", "CERVEZA CLARA", 48, "H87", 960.0), ("50161800", "TURRON DE ALMENDRA", 2, "H87", 200.0)])
# I: nota de crédito de res
cfdi("CAR000101XX1", "CARNES FINAS", [("50111513", "ARRACHERA DE RES", 2, "KGM", 560.0)], tipo="E")
# J: claves dudosas
cfdi("INM000101XX1", "INMOBILIARIA", [("01010101", "RENTA LOCAL AGOSTO", 1, "E48", 60000.0)])
cfdi("EMP000101XX1", "EMPAQUES", [("01010101", "BOLSAS DE PLASTICO", 1000, "H87", 1500.0),
                                  ("01010101", "WIDGET MISTERIOSO", 1, "H87", 900.0)])
cfdi("INM000101XX1", "INMOBILIARIA", [("90101501", "ARRENDAMIENTO BODEGA", 1, "E48", 12000.0)])
# K: servicios con clave normal; descuento
cfdi("CON000101XX1", "CONTADORES", [("80111600", "HONORARIOS CONTABLES", 1, "E48", 5000.0, 500.0)])
cfdi("SEG000101XX1", "SEGUROS", [("84131500", "SEGURO DE LOCAL", 1, "E48", 3000.0)])
# L: USD
cfdi("USA000101XX1", "PROVEEDOR USD", [("43211500", "LAPTOP", 1, "H87", 1000.0)], moneda="USD", tc=18.5)
# M: descartes
cfdi("CON000101XX1", "CONTADORES", [("84111506", "PAGO", 1, "ACT", 0)], tipo="P")
cfdi("CLI", "CLIENTE", [("84111505", "NOMINA", 1, "ACT", 10000)], tipo="N", receptor="EMP800101AAA")
cfdi(CLI, "CLIENTE", [("90101501", "VENTA RESTAURANTE", 1, "E48", 5000)], receptor="OTR000101XX1")   # emitida por el cliente
cfdi("FGA900101XX1", "FLAMA GAS", [("15111509", "GAS LP", 300, "LTR", 2850.0)], uuid="00000000-0000-0000-0000-000000000004", nombre="dup.xml")  # duplicado de D
cfdi("FGA900101XX1", "FLAMA GAS", [("15111509", "GAS LP", 100, "LTR", 950.0)], fecha="2026-05-01T10:00:00")  # fuera de periodo
(out / "basura.xml").write_text("<esto no es xml", encoding="utf-8")
# un zip anidado con una factura más
with zipfile.ZipFile(out / "lote.zip", "w") as z:
    z.writestr("sub/luz.xml", (out / "02.xml").read_text(encoding="utf-8").replace("000000000002", "000000000099"))
# N: gas natural en m3, contabilidad 8411, turron sin acento
cfdi("NAT000101XX1", "GAS NATURAL MX", [("83101600", "GAS NATURAL", 150, "MTQ", 1950.0)])
cfdi("CON000101XX1", "CONTADORES", [("84111500", "SERVICIOS CONTABLES", 1, "E48", 4000.0)])
cfdi("DUL000101XX1", "DULCERIA", [("50161800", "TURRON DE ALMENDRA", 2, "H87", 200.0)])
print("generados en", out)
