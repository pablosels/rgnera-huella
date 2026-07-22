# -*- coding: utf-8 -*-
"""
Calcula multiplicadores Scope 3 (Leontief, kg por USD) por sector para un
país a partir de Eora26 (worldmrio.com, precios básicos).

Uso:  python pipeline/eora26_pais.py data/eora26_2017 2017 MEX

Indicadores: CO2 (PRIMAP excl. LULUCF) y CO2e (Kyoto GHGs, AR4GWP100),
los mismos que usan los archivos oficiales de multiplicadores de Eora.
Unidades: Q en Gg, T en miles de USD -> m[Gg/k$] * 1000 = kg/USD.
"""
import sys
import io
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

FILA_CO2 = "Total emissions of CO2 excluding LULUCF (Gg) using PRIMAPv2.4"
FILA_CO2E = ("Total emissions of Kyoto GHGs excluding LULUCF CO2-e "
             "(Gg, AR4GWP100) using PRIMAPv2.4")


def cargar(dirdata: Path, anio: int, iso3: str):
    pref = dirdata / f"Eora26_{anio}_bp"
    labels = pd.read_csv(dirdata / "labels_T.txt", sep="\t", header=None,
                         names=["pais", "iso3", "entidad", "sector", "x1"])
    n = len(labels)
    print(f"[carga] {n} filas en labels_T; leyendo T...", flush=True)
    T = pd.read_csv(f"{pref}_T.txt", sep="\t", header=None,
                    dtype=np.float64).to_numpy()
    assert T.shape == (n, n), f"T shape {T.shape}"
    print("[carga] leyendo FD...", flush=True)
    FD = pd.read_csv(f"{pref}_FD.txt", sep="\t", header=None,
                     dtype=np.float64).to_numpy()

    # filas satélite necesarias (lectura en streaming, el archivo es enorme)
    qlab = pd.read_csv(dirdata / "labels_Q.txt", sep="\t", header=None,
                       names=["indicador", "detalle", "x1"])
    idx_co2 = qlab.index[(qlab["indicador"] == FILA_CO2)].tolist()
    idx_co2e = qlab.index[(qlab["indicador"] == FILA_CO2E)].tolist()
    assert len(idx_co2) == 1 and len(idx_co2e) == 1, (idx_co2, idx_co2e)
    quiero = {idx_co2[0]: "co2", idx_co2e[0]: "co2e"}
    filasQ = {}
    with open(f"{pref}_Q.txt", encoding="utf-8") as fh:
        for i, linea in enumerate(fh):
            if i in quiero:
                filasQ[quiero[i]] = np.fromstring(linea, sep="\t")
            if len(filasQ) == len(quiero):
                break
    Q_co2, Q_co2e = filasQ["co2"], filasQ["co2e"]
    assert len(Q_co2) == n and len(Q_co2e) == n
    return labels, T, FD, Q_co2, Q_co2e


def multiplicadores(T, FD, Q):
    x = T.sum(axis=1) + FD.sum(axis=1)
    xs = np.where(x > 0, x, 1.0)            # evita división entre cero
    q = np.where(x > 0, Q / xs, 0.0)        # Gg por k$ (directa)
    A = T / xs[np.newaxis, :]
    A[:, x <= 0] = 0.0
    n = len(x)
    print(f"[leontief] invirtiendo (I-A) de {n}x{n}...", flush=True)
    L = np.linalg.inv(np.eye(n) - A)
    m = q @ L                                # Gg por k$ (total, Scope 3)
    return x, q * 1000.0, m * 1000.0         # -> kg por USD


def main(dirdata, anio, iso3):
    dirdata = Path(dirdata)
    labels, T, FD, Q_co2, Q_co2e = cargar(dirdata, anio, iso3)
    x, q_co2, m_co2 = multiplicadores(T, FD, Q_co2)
    _, q_co2e, m_co2e = multiplicadores(T, FD, Q_co2e)

    sel = labels["iso3"] == iso3
    out = labels.loc[sel, ["iso3", "sector"]].copy()
    out["scope1_kgCO2_usd"] = q_co2[sel.to_numpy()]
    out["scope3_kgCO2_usd"] = m_co2[sel.to_numpy()]
    out["scope1_kgCO2e_usd"] = q_co2e[sel.to_numpy()]
    out["scope3_kgCO2e_usd"] = m_co2e[sel.to_numpy()]
    out["x_kUSD"] = x[sel.to_numpy()]

    ruta = Path(__file__).resolve().parent / f"sectores_{iso3}_{anio}_eora26.csv"
    out.to_csv(ruta, index=False, encoding="utf-8-sig")

    # sanity: emisiones nacionales por producción
    tot_co2 = Q_co2[sel.to_numpy()].sum() / 1000     # Gg -> Mt
    tot_co2e = Q_co2e[sel.to_numpy()].sum() / 1000
    print(f"\n[{iso3} {anio}] CO2 producción: {tot_co2:,.0f} Mt | "
          f"CO2e: {tot_co2e:,.0f} Mt")
    print(f"[ok] exportado {ruta.name}\n")
    pd.set_option("display.width", 160)
    print(out[["sector", "scope3_kgCO2_usd", "scope3_kgCO2e_usd"]]
          .sort_values("scope3_kgCO2e_usd", ascending=False)
          .to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
