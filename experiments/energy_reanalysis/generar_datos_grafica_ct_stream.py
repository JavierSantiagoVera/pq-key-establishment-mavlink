#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera los datos de la Fig. fig:ct_stream_cdf del manuscrito (CDF empirica de la
duracion de CT_stream) -- un comando, trazable a este archivo, sin numeros a mano.

Filtra a las rafagas EXITOSAS (pk_acks == PK_FRAGS, el mismo criterio de
TRAZABILIDAD_handshake.md) de las capturas R1-R5, que son las que el articulo declara
como la corrida de 100/96 sesiones. CT_stream, a diferencia de las otras 4 fases de
tab:kemtls_results, solo necesita ver los fragmentos CT_CHUNK en una direccion, asi que
alcanza una muestra mucho mayor (n=104) que las que exigen captura bidireccional (n=2).

Uso:
    python3 generar_datos_grafica_ct_stream.py
Escribe: ct_stream_R1R5_exitosas.csv (una columna, valor_s, ordenado)
Y tambien imprime las coordenadas (ms, fraccion_acumulada) listas para pegar en el
`\\addplot` de pgfplots del manuscrito, por si hay que regenerar la figura.
"""
import os
import glob
import statistics

from extraer_sesiones import eventos_hqc, segmentar, resumir, PK_FRAGS


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    cap = os.path.normpath(os.path.join(here, "..", "..", "firmware-fork", "captures"))

    files = sorted(glob.glob(os.path.join(cap, "*.pcapng")))

    vals = []
    excluidos = []
    for f in files:
        name = os.path.relpath(f, cap).replace("\\", "/")
        es_r1r5 = (name.startswith("fc_20251113_1")
                   and not name.startswith("fc_20251113_13")
                   and not name.startswith("fc_20251113_14"))
        if not es_r1r5:
            continue
        ev = eventos_hqc(f)
        if not ev:
            continue
        for r in segmentar(ev, 2.0):
            x = resumir(r)
            if x["ct_dur"] <= 0:
                continue
            if x["pk_acks"] == PK_FRAGS:
                vals.append(x["ct_dur"])
            else:
                excluidos.append((name, x["ct_dur"], x["pk_acks"]))

    vals.sort()
    n = len(vals)
    print(f"n exitosas (PK_ACK == {PK_FRAGS}): {n}")
    print(f"excluidas (handshake incompleto): {excluidos}")
    print(f"min/max: {vals[0]:.4f} / {vals[-1]:.4f} s")
    print(f"media: {statistics.mean(vals):.4f} s")
    print(f"mediana: {statistics.median(vals):.4f} s")

    out_path = os.path.join(here, "ct_stream_R1R5_exitosas.csv")
    with open(out_path, "w") as fo:
        fo.write("valor_s\n")
        for v in vals:
            fo.write(f"{v:.6f}\n")
    print(f"guardado {out_path}, n={n}")

    print("\ncoordenadas pgfplots (ms, fraccion acumulada):")
    coords = " ".join(f"({v*1000:.2f},{i/n:.4f})" for i, v in enumerate(vals, 1))
    print(coords)


if __name__ == "__main__":
    main()
