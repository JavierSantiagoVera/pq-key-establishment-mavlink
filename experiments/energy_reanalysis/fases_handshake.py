#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fases del handshake HQC, por msgid -- cierra el "Sin resolver" de
TRAZABILIDAD_handshake.md: las 4 filas de tab:kemtls_results que nunca se
midieron (HELLO->ACK, PK stream, DECAP->FINISH, FINISH->STATUS).

No necesita el Bebop ni datos nuevos: reusa las mismas capturas archivadas en
02_repo/.../captures/ y las mismas funciones de extraer_sesiones.py.

METODO: dentro de cada rafaga bidireccional (la unica donde HELLO 61000 y
FINISH 61005 son visibles), se toman min/max de timestamp por msgid y se
restan fronteras consecutivas:

    HELLO->ACK     = ts(61001) - ts(61000)
    PK stream      = max(ts(61002), ts(61007)) - ts(61001)
    CT stream      = max(ts(61003)) - min(ts(61003))          [igual que extraer_sesiones.py]
    DECAP->FINISH  = ts(61005) - max(ts(61003), ts(61004))
    FINISH->STATUS = ts(61006) - ts(61005)

Uso:
    python fases_handshake.py [directorio] [--gap 2.0]
"""
import os
import sys
import glob

from extraer_sesiones import eventos_hqc, segmentar, media, pct, PAPER, NOMBRE

# fila de tab:kemtls_results a contrastar (mean, p50, p95)
PAPER_FASES = {
    "HELLO->ACK":     (0.060,   0.0617,  0.0790),
    "PK stream":      (0.0186,  0.0186,  0.0192),
    "CT stream":      (0.409,   0.393,   0.421),
    "DECAP->FINISH":  (0.00172, 0.00164, 0.00233),
    "FINISH->STATUS": (0.135,   0.136,   0.142),
}


def fases_de_rafaga(rafaga, debug=False):
    """rafaga: lista de eventos (ts, msgid, plen, sentido). -> dict de fases o None."""
    t = {}
    for ts, msgid, _plen, _sentido in rafaga:
        if ts is None:
            return None  # TCP reensamblado sin timestamp por trama: no sirve aqui
        lo, hi = t.get(msgid, (ts, ts))
        t[msgid] = (min(lo, ts), max(hi, ts))

    # solo bidireccional: necesita HELLO y FINISH
    if 61000 not in t or 61005 not in t:
        return None

    if debug:
        t0 = t[61000][0]
        for k in sorted(t):
            lo, hi = t[k]
            print("      %-10s lo=%+.5f hi=%+.5f" % (NOMBRE.get(k, k), lo - t0, hi - t0))

    hello = t[61000][0]
    hello_ack = t.get(61001, (None, None))[0]
    pk_lo = t.get(61002, (None, None))[0]
    pk_hi = t.get(61002, (None, None))[1]
    ct_lo = t.get(61003, (None, None))[0]
    ct_hi = t.get(61003, (None, None))[1]
    ct_ack_hi = t.get(61004, (None, None))[1]
    finish = t[61005][0]
    status = t.get(61006, (None, None))[1]

    fases = {}
    if hello_ack is not None:
        fases["HELLO->ACK"] = hello_ack - hello
    if pk_lo is not None and pk_hi is not None:
        fases["PK stream"] = pk_hi - pk_lo          # span propio de PK_CHUNK, como CT stream
    if ct_lo is not None and ct_hi is not None and ct_hi > ct_lo:
        fases["CT stream"] = ct_hi - ct_lo
    if ct_ack_hi is not None:                        # frontera de decap = ultimo CT_ACK, no ultimo CT_CHUNK
        fases["DECAP->FINISH"] = finish - ct_ack_hi
    elif ct_hi is not None:
        fases["DECAP->FINISH"] = finish - ct_hi
    if status is not None:
        fases["FINISH->STATUS"] = status - finish
    return fases


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    gap = 2.0
    for a in sys.argv[1:]:
        if a.startswith("--gap"):
            gap = float(a.split("=", 1)[1]) if "=" in a else 2.0

    here = os.path.dirname(os.path.abspath(__file__))
    cap = args[0] if args else os.path.normpath(os.path.join(
        here, "..", "..", "firmware-fork", "captures"))

    files = sorted(glob.glob(os.path.join(cap, "*.pcapng")))
    files += sorted(glob.glob(os.path.join(cap, "previous_pcaps", "*.pcapng")))

    todas_fases = {k: [] for k in PAPER_FASES}
    encontradas = []

    for f in files:
        ev = eventos_hqc(f)
        if not ev:
            continue
        for rafaga in segmentar(ev, gap):
            name = os.path.relpath(f, cap).replace("\\", "/")
            if "--debug" in sys.argv:
                print("   -- %s --" % name)
            fs = fases_de_rafaga(rafaga, debug="--debug" in sys.argv)
            if fs is None:
                continue
            encontradas.append((name, fs))
            for k, v in fs.items():
                if v is not None and v >= 0:
                    todas_fases[k].append(v)

    print("Directorio: %s" % cap)
    print("Rafagas bidireccionales utilizables (HELLO y FINISH visibles): %d\n" % len(encontradas))
    for name, fs in encontradas:
        partes = ", ".join("%s=%.5f" % (k, v) for k, v in fs.items())
        print("   %-42s %s" % (name, partes))

    print("\n## Fases medidas vs tab:kemtls_results  (n = %d rafagas bidireccionales)"
          % len(encontradas))
    print("%-16s %8s %8s %8s   %-24s %8s %8s %8s" %
          ("Fase", "media", "p50", "p95", "", "art.mean", "art.p50", "art.p95"))
    print("-" * 100)
    for k, (am, ap50, ap95) in PAPER_FASES.items():
        xs = todas_fases[k]
        if not xs:
            print("%-16s %8s %8s %8s   %-24s %8.5f %8.5f %8.5f  -- SIN DATOS (n=0)" %
                  (k, "-", "-", "-", "", am, ap50, ap95))
            continue
        m, p50, p95 = media(xs), pct(xs, .5), pct(xs, .95)
        dev = abs(m - am) / am * 100 if am else float("nan")
        flag = "OK" if dev < 10 else ("REVISAR" if dev < 30 else "NO TRAZA")
        print("%-16s %8.5f %8.5f %8.5f   %-24s %8.5f %8.5f %8.5f  %s (%.0f%% desvio, n=%d)" %
              (k, m, p50, p95, "", am, ap50, ap95, flag, dev, len(xs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
