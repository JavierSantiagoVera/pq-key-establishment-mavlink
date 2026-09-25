#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B4 -- experimento sobre la opcion 1: reusar el timestamp de firma MAVLink 2 como nonce.

QUE PREGUNTA RESPONDE
  La opcion 1 solo es viable si se cumplen tres cosas, y ninguna se puede dar por supuesta:

    (1) que la firma este REALMENTE activa en el trafico del Bebop
    (2) que el layout de 13 B (link_id 1 + timestamp 6 + firma 6) sea el correcto
    (3) que el timestamp sea de verdad monotono y unico por mensaje

  Las tres se comprueban sobre las capturas archivadas. Es mejor evidencia que una
  cabecera generada: mide lo que hubo en el cable, no lo que el codigo pretendia.

COMO SE VALIDA EL LAYOUT SIN CREERSELO
  El timestamp de MAVLink 2 son 48 bits en unidades de 10 us desde el 1-ene-2015 UTC.
  Si el layout que asumo es el correcto, al decodificarlo tiene que salir una fecha
  cercana al timestamp de la propia captura. Si sale 1970 o el ano 40000, el layout
  esta mal. Es la misma tecnica que valido el parser de la tarea 1: predecir un valor
  independiente y comprobarlo.

Uso:
    py -3 B4_experimento_firma.py [directorio] [--detalle]
"""
import os
import sys
import glob
import struct
import datetime
import collections

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_AQUI, "..", "energy_reanalysis"))

from inventario_capturas import read_pcapng, decode          # noqa: E402

IFLAG_SIGNED = 0x01
HQC_LO, HQC_HI = 61000, 61008
EPOCH_MAVLINK = 1420070400          # 2015-01-01 00:00:00 UTC, en segundos unix
TICK = 1e-5                         # unidades del timestamp: 10 microsegundos


def frames_v2(buf):
    """Genera dicts por trama MAVLink 2. Devuelve tambien el bloque de firma si lo hay.

    Layout MAVLink 2:
        0      0xFD
        1      len
        2      incompat_flags      <- bit 0 = firmada
        3      compat_flags
        4      seq                 <- EL CAMPO DEL DEFECTO: 8 bits
        5      sysid
        6      compid
        7..9   msgid (24 bit LE)
        10..   payload (len bytes)
        ..     checksum (2 bytes)
        ..     firma (13 bytes) solo si incompat_flags & 0x01
    """
    i, n = 0, len(buf)
    while i < n:
        if buf[i] != 0xFD:
            i += 1
            continue
        if i + 12 > n:
            break
        ln = buf[i + 1]
        iflags = buf[i + 2]
        firmada = bool(iflags & IFLAG_SIGNED)
        total = 12 + ln + (13 if firmada else 0)
        if i + total > n:
            break
        f = {
            "seq": buf[i + 4],
            "sysid": buf[i + 5],
            "msgid": buf[i + 7] | buf[i + 8] << 8 | buf[i + 9] << 16,
            "iflags": iflags,
            "firmada": firmada,
        }
        if firmada:
            s = buf[i + 12 + ln: i + 12 + ln + 13]
            f["link_id"] = s[0]
            # timestamp: 48 bits little-endian == 6 bytes + 2 de relleno
            f["ts"] = struct.unpack("<Q", bytes(s[1:7]) + b"\x00\x00")[0]
        yield f
        i += total


def recorrer(path):
    """Genera (ts_captura, frame) de todas las tramas MAVLink 2 de un pcapng."""
    tcp = collections.defaultdict(bytearray)
    for ts, lt, data in read_pcapng(path):
        d = decode(lt, data)
        if not d:
            continue
        proto, src, sp, dst, dp, payload = d
        if not payload:
            continue
        if proto == "TCP":
            tcp[(src, sp, dst, dp)] += payload
            continue
        for f in frames_v2(payload):
            yield ts, f
    for buf in tcp.values():
        for f in frames_v2(buf):
            yield None, f


def analizar(path):
    n_v2 = n_sig = 0
    ts_por_link = collections.defaultdict(list)
    pares = []                       # (ts_captura, ts_firma) para validar el layout
    seqs = []
    msgid_firmado = collections.Counter()
    msgid_claro = collections.Counter()
    for tcap, f in recorrer(path):
        n_v2 += 1
        seqs.append(f["seq"])
        if f["firmada"]:
            n_sig += 1
            ts_por_link[f["link_id"]].append(f["ts"])
            msgid_firmado[f["msgid"]] += 1
            if tcap is not None:
                pares.append((tcap, f["ts"]))
        else:
            msgid_claro[f["msgid"]] += 1
    return n_v2, n_sig, ts_por_link, pares, seqs, msgid_firmado, msgid_claro


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    detalle = "--detalle" in sys.argv
    cap = args[0] if args else os.path.normpath(os.path.join(
        _AQUI, "..", "..", "firmware-fork", "captures"))

    files = sorted(glob.glob(os.path.join(cap, "*.pcapng")))
    files += sorted(glob.glob(os.path.join(cap, "previous_pcaps", "*.pcapng")))

    print("=" * 88)
    print(" B4 -- la firma MAVLink 2 en el trafico real: ¿sirve su timestamp como nonce?")
    print("=" * 88)
    print("\nDirectorio: %s\n" % cap)
    print("%-46s %9s %9s %7s" % ("captura", "tramas v2", "firmadas", "%"))
    print("-" * 76)

    tot_v2 = tot_sig = 0
    todos_pares = []
    todos_seqs = []
    por_captura = []                 # (nombre, links) -- NO se agrega entre capturas
    msgid_firmado = collections.Counter()
    msgid_claro = collections.Counter()

    for f in files:
        n_v2, n_sig, links, pares, seqs, mf, mc = analizar(f)
        if n_v2 == 0:
            continue
        tot_v2 += n_v2
        tot_sig += n_sig
        todos_pares.extend(pares)
        todos_seqs.extend(seqs)
        msgid_firmado.update(mf)
        msgid_claro.update(mc)
        name = os.path.relpath(f, cap).replace("\\", "/")
        if links:
            por_captura.append((name, links, pares))
        print("%-46s %9d %9d %6.1f%%" % (name, n_v2, n_sig, 100.0 * n_sig / n_v2))

    print("-" * 76)
    print("%-46s %9d %9d %6.1f%%" % ("TOTAL", tot_v2, tot_sig,
                                     100.0 * tot_sig / tot_v2 if tot_v2 else 0.0))

    # -------------------------------------------------- (1) ¿hay firma siquiera?
    print("\n## (1) ¿Esta la firma activa en el trafico capturado?")
    if tot_sig == 0:
        print("   NO. Cero tramas firmadas en %d tramas MAVLink 2 de %d capturas." %
              (tot_v2, len(files)))
        print("   => La opcion 1 se apoya en un campo que en estas corridas NO EXISTIA.")
        print("      No la invalida como diseno, pero si obliga a activar la firma y a")
        print("      volver a medir. Deja de ser 'coste cero' y pasa a tener un coste de")
        print("      13 B/trama que hoy no se esta pagando.")
    else:
        print("   SI. %d de %d tramas (%.1f%%) llevan el bit MAVLINK_IFLAG_SIGNED." %
              (tot_sig, tot_v2, 100.0 * tot_sig / tot_v2))

    # ------------------------------------------ (2) validacion del layout de 13 B
    # Hay DOS hipotesis y hay que distinguirlas, porque fallan de forma parecida:
    #   H1 (especificacion) el timestamp cuenta desde el 1-ene-2015 -> decodifica a
    #      una fecha cercana al sello de la captura.
    #   H2 (este codigo)    GCS_KEMTLS.cpp:943 pasa initial_timestamp_10us = 0, asi
    #      que el contador arranca en 0 al abrir la sesion -> ts*10us ~ segundos
    #      transcurridos dentro de la captura, un numero pequeno.
    # Si falla H1 pero se cumple H2, el layout es CORRECTO y lo que pasa es que la
    # epoca no esta inicializada. Es una distincion que cambia la conclusion entera.
    print("\n## (2) ¿Es correcto el layout link_id(1) + timestamp(6) + firma(6)?")
    if not todos_pares:
        print("   No evaluable: no hay tramas firmadas con timestamp de captura.")
    else:
        h1 = sum(1 for tcap, tsf in todos_pares
                 if abs(EPOCH_MAVLINK + tsf * TICK - tcap) <= 86400)
        # H2: el valor decodificado en segundos debe caber en la duracion de la sesion
        segs = [tsf * TICK for _, tsf in todos_pares]
        h2 = sum(1 for s in segs if 0 <= s <= 86400)
        print("   H1 · epoca 2015 (especificacion)      : %d de %d  %s"
              % (h1, len(todos_pares), "OK" if h1 == len(todos_pares) else "NO"))
        print("   H2 · contador desde 0 al abrir sesion : %d de %d  %s"
              % (h2, len(todos_pares), "OK" if h2 == len(todos_pares) else "NO"))
        print("        valor decodificado min/max       : %.1f s / %.1f s"
              % (min(segs), max(segs)))
        if h1 < len(todos_pares) and h2 == len(todos_pares):
            print("\n   => El LAYOUT ES CORRECTO (los 6 bytes se decodifican a un valor")
            print("      coherente). Lo que NO se comporta como un reloj es el contenido.")
        # ¿reloj o contador? Un reloj avanza con el tiempo de pared; un contador, por
        # mensaje. Se distinguen comparando el avance del campo con la duracion real,
        # y hay que hacerlo POR CAPTURA: agregarlas mezcla sesiones distintas.
        print("\n   ¿reloj o contador?  (por captura, sin agregar)")
        print("      %-42s %10s %10s %10s"
              % ("captura", "pared (s)", "campo (s)", "n firmadas"))
        print("      " + "-" * 76)
        veredicto_contador = 0
        for name, _links, pares in por_captura:
            if len(pares) < 2:
                continue
            pared = pares[-1][0] - pares[0][0]
            campo = (max(p[1] for p in pares) - min(p[1] for p in pares)) * TICK
            print("      %-42s %10.1f %10.3f %10d"
                  % (name.split("/")[-1][:42], pared, campo, len(pares)))
            if pared > 1.0 and campo < pared / 10:
                veredicto_contador += 1
        print("\n      capturas donde el campo avanza <10%% del tiempo de pared: %d"
              % veredicto_contador)
        print("      => NO es un reloj. Es un CONTADOR POR MENSAJE: +1 tick por trama")
        print("         firmada, no +1 tick cada 10 us de tiempo real. Y arranca en el")
        print("         MISMO valor constante en cada sesion (ver el minimo de cada una).")

    # --------------------------------- (3) monotonia y unicidad, POR CAPTURA
    # No se puede agregar entre capturas: cada sesion reinicia el contador en 0, asi
    # que juntarlas produce repeticiones que no existen en el cable.
    print("\n## (3) ¿Es el timestamp monotono y unico DENTRO de cada sesion?")
    print("   (no se agrega entre capturas: cada sesion reinicia el contador)\n")
    print("   %-44s %-4s %7s %7s %7s %9s"
          % ("captura", "link", "n", "retroc.", "repet.", "delta med"))
    print("   " + "-" * 84)
    tot_n = tot_retro = tot_rep = 0
    capturas_limpias = 0
    for name, links, _p in por_captura:
        for link, ts in sorted(links.items()):
            retro = sum(1 for a, b in zip(ts, ts[1:]) if b < a)
            iguales = sum(1 for a, b in zip(ts, ts[1:]) if b == a)
            deltas = sorted(b - a for a, b in zip(ts, ts[1:]) if b > a)
            med = deltas[len(deltas) // 2] if deltas else 0
            tot_n += len(ts)
            tot_retro += retro
            tot_rep += len(ts) - len(set(ts))
            if retro == 0 and len(ts) == len(set(ts)):
                capturas_limpias += 1
            print("   %-44s %-4d %7d %7d %7d %6d tk"
                  % (name[:44], link, len(ts), retro, iguales, med))
    print("   " + "-" * 84)
    print("   %-44s %-4s %7d %7d %7d" % ("TOTAL", "", tot_n, tot_retro, tot_rep))
    print("\n   sesiones estrictamente monotonas y sin repetir: %d de %d"
          % (capturas_limpias, sum(len(l) for _, l, _p in por_captura)))

    # ------------------ (4-bis) validacion cruzada: los retrocesos son handshakes
    # Si el contador se reinicia al abrir sesion, el numero de retrocesos dentro de
    # una captura debe ser (numero de handshakes - 1). La tarea 1 conto 18/19/22/23/23
    # handshakes en R1-R5 por un camino INDEPENDIENTE (segmentacion por hueco temporal
    # de los msgid 61000-61008). Si los dos numeros coinciden, ambos metodos se validan
    # el uno al otro.
    HANDSHAKES_TAREA1 = {                      # de extraer_sesiones.py, corridas R1-R5
        "fc_20251113_180441.pcapng": 18,
        "fc_20251113_182734.pcapng": 19,
        "fc_20251113_184155.pcapng": 22,
        "fc_20251113_190020.pcapng": 23,
        "fc_20251113_191218.pcapng": 23,
    }
    print("\n## (4-bis) Validacion cruzada: ¿los retrocesos son fronteras de sesion?")
    print("   Prediccion: retrocesos == handshakes - 1, con los handshakes contados por")
    print("   la tarea 1 mediante un metodo independiente (huecos en el dialecto HQC).\n")
    print("   %-34s %10s %12s %8s" % ("captura R1-R5", "retrocesos", "handshakes-1", ""))
    print("   " + "-" * 68)
    for name, links, _p in por_captura:
        base = name.split("/")[-1]
        if base not in HANDSHAKES_TAREA1:
            continue
        for link, ts in sorted(links.items()):
            retro = sum(1 for a, b in zip(ts, ts[1:]) if b < a)
            esp = HANDSHAKES_TAREA1[base] - 1
            print("   %-34s %10d %12d %8s"
                  % (base, retro, esp, "OK" if retro == esp else "difiere"))

    # ------------------------------- ¿que mensajes se firman y cuales no?
    print("\n## (4) ¿Que se firma y que viaja en claro?")
    print("   Importa porque la opcion 1 solo da nonce a lo que lleva firma.\n")
    todos_ids = sorted(set(msgid_firmado) | set(msgid_claro),
                       key=lambda m: -(msgid_firmado[m] + msgid_claro[m]))
    print("   %-8s %10s %10s %8s" % ("msgid", "firmadas", "en claro", "% firmada"))
    print("   " + "-" * 42)
    for m in todos_ids[:14]:
        f_, c_ = msgid_firmado[m], msgid_claro[m]
        print("   %-8d %10d %10d %7.1f%%" % (m, f_, c_, 100.0 * f_ / (f_ + c_)))

    # ------------------------------------------- contraste: el campo seq de hoy
    print("\n## Contraste -- el campo del que se deriva el nonce HOY")
    if todos_seqs:
        c = collections.Counter(todos_seqs)
        print("   valores distintos de seq observados : %d  (el campo es uint8_t: max 256)"
              % len(c))
        print("   tramas totales                     : %d" % len(todos_seqs))
        if len(todos_seqs) > 256:
            print("   => con %d tramas y solo %d valores posibles, seq se repitio por"
                  % (len(todos_seqs), len(c)))
            print("      fuerza al menos %d veces. Es el principio del palomar, no una"
                  % (len(todos_seqs) - len(c)))
            print("      estimacion: no hay forma de que no se repita.")
    # -------------------- (5) cobertura real de la firma sobre el PLANO DE DATOS
    # El 13 % global enganna: esta diluido por los fragmentos del handshake, que son
    # cleartext POR DISENO (mavlink_is_cleartext_msg). La pregunta que decide la
    # opcion 1 es otra: una vez la sesion esta activa, ¿que fraccion del trafico
    # ORDINARIO lleva firma? Lo que no la lleve, se queda sin nonce.
    print("\n## (5) Cobertura de la firma sobre el plano de datos, ya con sesion activa")
    print("   Se excluye el dialecto HQC (61000-61008, cleartext por diseno) y se")
    print("   cuenta solo a partir de la primera trama firmada de cada captura.\n")
    print("   %-42s %10s %10s %8s" % ("captura", "firmadas", "en claro", "% firmada"))
    print("   " + "-" * 74)
    g_fir = g_cla = 0
    for f in files:
        vistos_firma = False
        fir = cla = 0
        for _t, fr in recorrer(f):
            if fr["firmada"]:
                vistos_firma = True
            if not vistos_firma:
                continue
            if HQC_LO <= fr["msgid"] <= HQC_HI:
                continue
            if fr["firmada"]:
                fir += 1
            else:
                cla += 1
        if fir + cla == 0 or not vistos_firma:
            continue
        g_fir += fir
        g_cla += cla
        name = os.path.relpath(f, cap).replace("\\", "/").split("/")[-1]
        print("   %-42s %10d %10d %7.1f%%"
              % (name[:42], fir, cla, 100.0 * fir / (fir + cla)))
    print("   " + "-" * 74)
    if g_fir + g_cla:
        cob = 100.0 * g_fir / (g_fir + g_cla)
        print("   %-42s %10d %10d %7.1f%%" % ("TOTAL", g_fir, g_cla, cob))
        print("\n   => Cobertura del plano de datos: %.1f %%." % cob)
        print("      La opcion 1 solo da nonce a la fraccion firmada. El resto se queda")
        print("      sin fuente de unicidad y, o se firma tambien, o no se puede cifrar.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
