#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extractor de sesiones de handshake HQC -- Tarea 1.

Contrasta las cifras del articulo (tab:kemtls_results) contra las capturas:

    intentos / exitos            100 / 96
    handshake total  media/p50/p95   0.624 / 0.611 / 0.632 s
    fase CT_stream   media           0.409 s
    throughput de ciphertext        0.177 Mbps

METODO: los handshakes son rafagas de ~0.6 s separadas por ~15 s, asi que se
segmenta por hueco temporal. NO hace falta parsear session_id ni conocer el
layout de los payloads -- que es lo que haria falta si el dialecto hqc.xml
estuviera disponible, y no lo esta.

PREDICCION que valida el parser antes de creerle (de los tamanos reales de
HQC-128 en libraries/AP_KEM/.../api.h, con el MTU 220 del articulo):

    fragmentos de pk    2249/220 -> 11     == msgid 61002 y 61007
    fragmentos de ct    2*4433/220 -> 42   == msgid 61004
    goodput de ct       2*4433 = 8866 B

Si una rafaga no da 11 PK_ACK, el metodo esta mal y no hay que seguir.

Uso:
    python extraer_sesiones.py [directorio] [--gap 2.0] [--detalle]
"""
import os
import sys
import glob
import collections

from inventario_capturas import read_pcapng, decode, mav_frames

HQC_LO, HQC_HI = 61000, 61008

# nombres del dialecto segun tab:hqc-msgs del manuscrito
NOMBRE = {
    61000: "HELLO",     61001: "HELLO_ACK", 61002: "PK_CHUNK",
    61003: "CT_CHUNK",  61004: "CT_ACK",    61005: "FINISH",
    61006: "STATUS",    61007: "PK_ACK",    61008: "ABORT",
}

# tamanos reales vendorizados de HQC-128
PK_BYTES, CT_BYTES, MTU = 2249, 4433, 220
PK_FRAGS = -(-PK_BYTES // MTU)          # 11
CT_FRAGS = -(-CT_BYTES // MTU) * 2      # 42, por ct_e + ct_s
CT_GOODPUT = CT_BYTES * 2               # 8866 B

# cifras publicadas que hay que contrastar
PAPER = {
    "intentos": 100, "exitos": 96,
    "hs_media": 0.624, "hs_p50": 0.611, "hs_p95": 0.632,
    "ct_media": 0.409, "mbps": 0.177,
}


def pct(xs, p):
    """Percentil por interpolacion lineal, sin numpy."""
    if not xs:
        return float("nan")
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def media(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def eventos_hqc(path):
    """-> lista de (ts, msgid, payload_len, sentido) ordenada por ts."""
    ev = []
    tcp = collections.defaultdict(bytearray)
    for ts, lt, data in read_pcapng(path):
        d = decode(lt, data)
        if not d:
            continue
        proto, src, sp, dst, dp, payload = d
        if not payload:
            continue
        if proto == "TCP":                       # se reensambla y se procesa al final
            tcp[(src, sp, dst, dp)] += payload
            continue
        sentido = "%s->%s" % (src, dst)
        for _, _, msgid, plen in mav_frames(payload):
            if HQC_LO <= msgid <= HQC_HI:
                ev.append((ts, msgid, plen, sentido))

    for (src, sp, dst, dp), buf in tcp.items():  # TCP: sin timestamp por trama
        sentido = "%s->%s" % (src, dst)
        for _, _, msgid, plen in mav_frames(buf):
            if HQC_LO <= msgid <= HQC_HI:
                ev.append((None, msgid, plen, sentido))

    ev.sort(key=lambda e: (e[0] is None, e[0]))
    return ev


def segmentar(ev, gap):
    """Agrupa eventos en rafagas separadas por mas de `gap` segundos."""
    rafagas, actual, ultimo = [], [], None
    for e in ev:
        if e[0] is None:                         # TCP reensamblado: una sola rafaga
            actual.append(e)
            continue
        if ultimo is not None and e[0] - ultimo > gap:
            rafagas.append(actual)
            actual = []
        actual.append(e)
        ultimo = e[0]
    if actual:
        rafagas.append(actual)
    return rafagas


def resumir(rafaga):
    """-> dict con duraciones, conteos y bytes de una rafaga."""
    ts = [e[0] for e in rafaga if e[0] is not None]
    n = collections.Counter(e[1] for e in rafaga)
    ct_ts = [e[0] for e in rafaga if e[1] == 61003 and e[0] is not None]
    ct_bytes = sum(e[2] for e in rafaga if e[1] == 61003)
    return {
        "n": n,
        "dur": (max(ts) - min(ts)) if len(ts) > 1 else 0.0,
        "ct_dur": (max(ct_ts) - min(ct_ts)) if len(ct_ts) > 1 else 0.0,
        "ct_bytes": ct_bytes,
        "ct_chunks": n.get(61003, 0),
        "pk_acks": n.get(61007, 0),
        "ct_acks": n.get(61004, 0),
        "sentidos": set(e[3] for e in rafaga),
    }


def analizar(path, gap):
    ev = eventos_hqc(path)
    if not ev:
        return None
    return [resumir(r) for r in segmentar(ev, gap)]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    detalle = "--detalle" in sys.argv
    gap = 2.0
    for a in sys.argv[1:]:
        if a.startswith("--gap"):
            gap = float(a.split("=", 1)[1]) if "=" in a else 2.0

    here = os.path.dirname(os.path.abspath(__file__))
    cap = args[0] if args else os.path.normpath(os.path.join(
        here, "..", "..", "firmware-fork", "captures"))

    files = sorted(glob.glob(os.path.join(cap, "*.pcapng")))
    files += sorted(glob.glob(os.path.join(cap, "previous_pcaps", "*.pcapng")))

    print("Directorio: %s" % cap)
    print("Hueco de segmentacion: %.1f s\n" % gap)
    print("%-44s %7s %9s %9s %7s %7s" %
          ("captura", "rafagas", "dur media", "CT media", "PK_ACK", "CT_chk"))
    print("-" * 92)

    todas = []
    for f in files:
        r = analizar(f, gap)
        if not r:
            continue
        name = os.path.relpath(f, cap).replace("\\", "/")
        print("%-44s %7d %9.3f %9.3f %7.1f %7.1f" % (
            name, len(r), media([x["dur"] for x in r]),
            media([x["ct_dur"] for x in r]),
            media([x["pk_acks"] for x in r]),
            media([x["ct_chunks"] for x in r])))
        if detalle:
            for i, x in enumerate(r, 1):
                ids = ", ".join("%s:%d" % (NOMBRE.get(k, k), v)
                                for k, v in sorted(x["n"].items()))
                print("      #%-3d dur %6.3f  CT %6.3f  %s" % (i, x["dur"], x["ct_dur"], ids))
        todas.extend((name, x) for x in r)

    # ---------------------------------------------------- validacion del metodo
    print("\n## Validacion del metodo (prediccion de los tamanos de HQC-128)")
    conpk = [x for _, x in todas if x["pk_acks"]]
    okpk = sum(1 for x in conpk if x["pk_acks"] == PK_FRAGS)
    print("   fragmentos de pk esperados : %d   (2249 B / MTU 220)" % PK_FRAGS)
    print("   rafagas con PK_ACK         : %d, de las cuales %d dan exactamente %d  %s"
          % (len(conpk), okpk, PK_FRAGS, "OK" if okpk == len(conpk) and conpk else "REVISAR"))
    conct = [x for _, x in todas if x["ct_acks"]]
    if conct:
        okct = sum(1 for x in conct if x["ct_acks"] == CT_FRAGS)
        print("   fragmentos de ct esperados : %d   (2 x 4433 B / MTU 220)" % CT_FRAGS)
        print("   rafagas con CT_ACK         : %d, de las cuales %d dan exactamente %d  %s"
              % (len(conct), okct, CT_FRAGS, "OK" if okct == len(conct) else "REVISAR"))

    # las rafagas que no dan 11 PK_ACK son candidatas a handshake fallido
    raros = [(n, x) for n, x in todas if x["pk_acks"] and x["pk_acks"] != PK_FRAGS]
    if raros:
        print("\n   rafagas anomalas (PK_ACK != %d) -- candidatas a fallo:" % PK_FRAGS)
        for n, x in raros:
            print("      %-42s PK_ACK %d  dur %.3f  CT_chunks %d"
                  % (n, x["pk_acks"], x["dur"], x["ct_chunks"]))

    # ---------------------------------------------- direccion de la captura
    # Las fc_2025113_* solo capturan FC->GCS: falta HELLO (61000) al principio y
    # FINISH (61005) al final, asi que su "duracion" es una ventana truncada y
    # NO es comparable con el total del articulo. Las clear_fc_* ven las dos.
    def bidir(x):
        return bool(x["n"].get(61000) or x["n"].get(61004) or x["n"].get(61005))

    R1R5 = [(n, x) for n, x in todas if n.startswith("fc_20251113_1")
            and not n.startswith("fc_20251113_13") and not n.startswith("fc_20251113_14")]
    bi = [(n, x) for n, x in todas if bidir(x)]
    uni = [(n, x) for n, x in todas
           if (n.startswith("fc_") or n.startswith("clear_fc_")) and not bidir(x)]

    def bloque(titulo, conj, comparar_total):
        if not conj:
            return
        durs = [x["dur"] for _, x in conj if x["dur"] > 0]
        ctds = [x["ct_dur"] for _, x in conj if x["ct_dur"] > 0]
        print("\n%s  (n = %d)" % (titulo, len(conj)))
        if durs:
            nota = "(articulo: %.3f / %.3f / %.3f)" % (
                PAPER["hs_media"], PAPER["hs_p50"], PAPER["hs_p95"]) if comparar_total \
                else "(ventana truncada: falta HELLO y FINISH -- NO comparable)"
            print("   duracion media/p50/p95 : %.3f / %.3f / %.3f s   %s"
                  % (media(durs), pct(durs, .5), pct(durs, .95), nota))
        if ctds:
            print("   CT_stream media        : %.3f s   (articulo: %.3f)"
                  % (media(ctds), PAPER["ct_media"]))
            good = media([CT_GOODPUT * 8 / d / 1e6 for d in ctds])
            print("   throughput goodput     : %.3f Mbps   (articulo: %.3f)"
                  % (good, PAPER["mbps"]))
        # retransmision solo donde se ven AMBAS direcciones
        pares = [(x["ct_chunks"], x["ct_acks"]) for _, x in conj if x["ct_acks"]]
        if pares:
            env = sum(p[0] for p in pares)
            ack = sum(p[1] for p in pares)
            print("   fragmentos CT env/ack  : %d / %d  ->  %.2fx de retransmision"
                  % (env, ack, env / float(ack)))

    print("\n## Contraste con tab:kemtls_results")
    print("   El articulo declara 100 intentos / 96 exitos. Las cinco corridas de estres")
    print("   R1-R5 suman %d rafagas." % len(R1R5))
    bloque("### R1-R5, capturas fc_* (solo FC->GCS)", R1R5, comparar_total=False)
    bloque("### Capturas con las dos direcciones (dialogo completo)", bi, comparar_total=True)
    bloque("### Resto de capturas de hardware (una direccion)", uni, comparar_total=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
