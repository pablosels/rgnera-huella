# RGNERA Empresas: huella de carbono con los CFDI del cliente

## Qué hay aquí

| Archivo | Para qué |
| --- | --- |
| `huella_xml.py` | La herramienta: lee los XML del SAT del cliente y arma el Excel del reporte. |
| `factores.py` | Factores de emisión y tablas de clasificación, con sus fuentes. |
| `sectores_MEX_2018_mip.csv` | Intensidades por sector (MIP 2018 del INEGI + INECC). Es copia del motor de la calculadora (`rgnera-huella/pipeline`). |
| `sin_factura_ejemplo.json` | Plantilla para las compras que no tienen factura. |

`piloto.py` (el cálculo del piloto con dos negocios reales, desde sus P&L) y sus
resultados (`resultados_*.json`) tienen datos privados de los negocios: viven en
`Dropbox\RGNERA\Empresas\Herramienta huella\` y **nunca** se suben a este repo,
que es público (están en `.gitignore`).

## Cómo se usa

1. El cliente baja del portal del SAT sus facturas **recibidas** del periodo (Factura electrónica → Consultar facturas recibidas, o la descarga masiva) y te manda el .zip.
2. Corres:

   ```
   python huella_xml.py cliente.zip --rfc RFC_DEL_CLIENTE --desde 2025-10-01 --hasta 2026-09-30 --ventas 2500000 --salida "Huella Cliente.xlsx"
   ```

   - `--rfc` es obligatorio: solo cuenta las facturas donde el cliente es el receptor.
   - `--ventas` (ventas anuales sin IVA) agrega los kg de CO2e por cada $1,000 de venta.
   - `--anualizar` escala el periodo a 12 meses si te mandaron menos de un año.
   - `--extra sin_factura.json` suma lo que no tiene factura: compras en efectivo, kWh de recibos sin XML, basura. Las cantidades van por el mismo periodo que las facturas, porque `--anualizar` también las escala.
3. Revisa la hoja **Por revisar** del Excel. Ahí caen las claves del SAT "sin catálogo", los kilos o kWh estimados con precio y los conceptos que pesan más del 10% del gasto.
4. El Excel trae las hojas Resumen, Por categoría, Detalle, Por revisar y Supuestos.

Requisitos: Python 3 con `openpyxl`.

## Qué hace con cada concepto

- **Electricidad (alcance 2):** kWh de la factura. Si no son creíbles, los estima del importe a $4.6 por kWh y lo marca. CFE suele poner "1 KWH" con todo el cargo en el importe.
- **Gas LP, gas natural y combustibles (alcance 1):** litros, kilos o m³ de la factura; si no vienen, los estima con el precio.
- **Alimentos (alcance 3):** si la factura trae kilos, calcula por kilo con Poore y Nemecek 2018. Si no, estima los kilos con el precio mediano por kilo de ese grupo en las compras del mismo cliente. Si tampoco se puede, usa pesos por la intensidad del sector.
- **Todo lo demás (alcance 3):** pesos sin IVA por la intensidad del sector SCIAN que sale de la ClaveProdServ. Cuando la clave es "sin catálogo" (01010101) o una que suele estar mal usada (restaurantes, 9010), manda la descripción.
- **Se descartan:** complementos de pago, nómina, traslados y las facturas que el cliente emitió. Las notas de crédito restan.

## Probado

- **28 de octubre de 2026**, con 63 CFDI reales de dos clientes del piloto: lee el XML, filtra por RFC, saca los litros de gas LP del proveedor de gas, estima la luz de los recibos de CFE y corrige las rentas mal codificadas. Esa muestra no es el trimestre completo, así que no se compara contra el resultado del piloto. Para eso hace falta bajar del SAT todos los XML de julio a septiembre.
- **9 de noviembre de 2026**, con 25 CFDI sintéticos (`pruebas/gen_cfdi.py`) que cubren los casos difíciles: los tres modos de CFE, gas LP en litros y kilos, gasolina/diésel, gas natural, alimentos por kilo y por pieza, notas de crédito, claves 01010101 y 90101501, descuentos, dólares y los seis tipos de descarte. La lectura y los cálculos salieron bien; se corrigieron cinco fallas de clasificación:
  1. "Filete de salmón" salía como **res** (99 kg/kg en vez de 13.6) y "lomo de atún" y "costilla de res" como **cerdo**: ahora las especies nombradas (res, pescados) mandan sobre las palabras genéricas (filete, lomo, costilla, carne).
  2. Un concepto "COMBUSTIBLE" sin palabra clave caía en gas LP aunque la clave fuera de gasolina (1510): ahora el tipo por defecto sale de la clave.
  3. El gas LP de `--extra` se etiquetaba "gas lp" y partía la categoría en dos filas del reporte.
  4. "Turrón" se clasificaba como bebida por la palabra "ron".
  5. Servicios contables (clave 8411) iban a banca (522); ahora a servicios profesionales (541).

Para repetir la prueba: los dos comandos del encabezado de `pruebas/gen_cfdi.py`.
