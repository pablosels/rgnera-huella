# Calculadora de Huella Ambiental · RGNERA 🌿

**[→ Usar la calculadora](https://pablosels.github.io/rgnera-huella/)** · parte de [rgnera.com](https://www.rgnera.com), biblioteca digital de sustentabilidad.

Estima la huella de carbono personal mensual (kg CO₂e) a partir del gasto en 19
categorías cotidianas, usando **análisis insumo-producto ambientalmente extendido
(EEIO, modelo de Leontief)** con datos 100% oficiales y públicos de México.

## Metodología

```
q = Q · inv(diag(x))      intensidades directas (emisiones por peso producido)
A = T · inv(diag(x))      coeficientes técnicos
L = inv(I − A)            inversa de Leontief (cadena de suministro completa)
m = q · L                 intensidad total: g CO₂e por peso de demanda final
huella = Σ m_cat · gasto  (+ combustión directa de gasolina/gas/electricidad)
```

- **Matriz Insumo-Producto 2018** (INEGI): 78 subsectores SCIAN, producto×producto,
  precios básicos.
- **Inventario Nacional de Emisiones INEGyCEI 2018** (INECC): 764 Mt CO₂e asignadas
  a sectores económicos vía puente IPCC→SCIAN (cobertura 100%, ver
  `pipeline/mexico_mip.py`).
- **Energía directa**: electricidad 0.444 kg CO₂e/kWh (Aviso FESEN 2024,
  CRE/SEMARNAT); gasolina 2.31 kg CO₂/L de combustión + cadena; gas LP.
- Ajustes por márgenes de comercio e inflación; ponderación de categorías por el
  consumo privado real de la MIP.

## Estructura

| Ruta | Qué es |
|---|---|
| `docs/` | El sitio publicado (HTML autocontenido, sin dependencias) |
| `web/plantilla.html` | Plantilla fuente de la calculadora |
| `web/intensidades_MEX.json` | Intensidades por categoría (generadas y auditadas) |
| `pipeline/` | Scripts de cálculo: puente INECC→SCIAN, Leontief, categorías, auditoría |

Los datos crudos (MIP de INEGI, INEGyCEI de INECC, Eora26) no se redistribuyen
aquí; los scripts documentan cómo obtenerlos y reproducir todo.

## Limitaciones

Estimación educativa con intensidades promedio por sector: no distingue marcas ni
hábitos específicos dentro de una categoría. Resultados orientativos, no
contabilidad oficial. Supuestos documentados en el código (reparto del
autotransporte, refrigerantes, bunkers de aviación).

---
Hecho con 💚 por [RGNERA](https://www.rgnera.com) · [@rgnera](https://www.instagram.com/rgnera/)
