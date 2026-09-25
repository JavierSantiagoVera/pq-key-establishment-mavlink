#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inventario de capturas -- Tarea 1 (trazabilidad de las cifras de handshake).

SIN DEPENDENCIAS: lee pcapng con la biblioteca estandar. No necesita scapy,
pymavlink ni tshark.

Motivo de existir: verify_handshake.py filtra "if UDP not in pkt: continue",
asi que es CIEGO a las capturas de handshake HQC, que son TCP sobre
127.0.0.1:5762 (SITL). Este script no asume transporte: reporta el que haya.

Para cada captura:
  - transporte y extremos reales (IP:puerto)   <- de aqui sale QUE DISPOSITIVO es
  - tramas MAVLink v1/v2 y su histograma de msgid
  - mensajes del dialecto HQC (61000-61008)
  - duracion de la captura

Uso:
    python inventario_capturas.py [directorio] [--detalle]
"""
import os, sys, glob, struct, collections

HQC_LO, HQC_HI = 61000, 61008


# ---------------------------------------------------------------- pcapng ----
def read_pcapng(path):
    """Genera (timestamp, linktype, bytes_del_paquete)."""
    with open(path, "rb") as f:
        endian, ifaces = "<", []
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                return
            btype = struct.unpack(endian + "I", hdr[:4])[0]

            if btype == 0x0A0D0D0A:                      # Section Header
                bom = f.read(4)
                endian = "<" if bom == b"\x4d\x3c\x2b\x1a" else ">"
                blen = struct.unpack(endian + "I", hdr[4:8])[0]
                f.read(blen - 16)
                f.read(4)
                ifaces = []
                continue

            blen = struct.unpack(endian + "I", hdr[4:8])[0]
            if blen < 12:
                return
            body = f.read(blen - 12)
            f.read(4)

            if btype == 1:                               # Interface Description
                linktype = struct.unpack(endian + "H", body[0:2])[0]
                tsresol, opts, i = 6, body[8:], 0
                while i + 4 <= len(opts):
                    code, olen = struct.unpack(endian + "HH", opts[i:i + 4])
                    if code == 0:
                        break
                    if code == 9 and olen >= 1:
                        tsresol = opts[i + 4]
                    i += 4 + ((olen + 3) // 4) * 4
                ifaces.append((linktype, tsresol))

            elif btype == 6:                             # Enhanced Packet
                iface, tsh, tsl, caplen, _ = struct.unpack(endian + "IIIII", body[:20])
                lt, tsresol = ifaces[iface] if iface < len(ifaces) else (1, 6)
                div = float(2 ** (tsresol & 0x7F)) if tsresol & 0x80 else float(10 ** tsresol)
                yield ((tsh << 32 | tsl) / div, lt, body[20:20 + caplen])

            elif btype == 3:                             # Simple Packet
                lt = ifaces[0][0] if ifaces else 1
                yield (None, lt, body[4:])


# ------------------------------------------------------- capa de enlace ----
def decode(lt, data):
    """-> (proto, src, sport, dst, dport, payload) | None. Solo IPv4."""
    try:
        if lt == 1:                                      # Ethernet
            et, off = int.from_bytes(data[12:14], "big"), 14
            while et in (0x8100, 0x88A8):                # VLAN
                et, off = int.from_bytes(data[off + 2:off + 4], "big"), off + 4
        elif lt == 113:                                  # Linux cooked v1
            et, off = int.from_bytes(data[14:16], "big"), 16
        elif lt == 276:                                  # Linux cooked v2
            et, off = int.from_bytes(data[0:2], "big"), 20
        elif lt == 101:                                  # RAW IP
            et, off = (0x0800 if data[0] >> 4 == 4 else 0x86DD), 0
        elif lt == 0:                                    # NULL / loopback BSD
            fam = int.from_bytes(data[0:4], "little")
            et, off = (0x0800 if fam == 2 else 0x86DD), 4
        else:
            return None
        if et != 0x0800:
            return None

        ip = data[off:]
        ihl, proto = (ip[0] & 0x0F) * 4, ip[9]
        src = ".".join(str(b) for b in ip[12:16])
        dst = ".".join(str(b) for b in ip[16:20])
        tot = int.from_bytes(ip[2:4], "big")
        seg = ip[ihl:tot] if 0 < tot <= len(ip) else ip[ihl:]

        if proto == 17 and len(seg) >= 8:                # UDP
            sport, dport, ulen = struct.unpack(">HHH", seg[0:6])
            return ("UDP", src, sport, dst, dport, seg[8:ulen] if ulen >= 8 else seg[8:])
        if proto == 6 and len(seg) >= 20:                # TCP
            sport, dport = struct.unpack(">HH", seg[0:4])
            return ("TCP", src, sport, dst, dport, seg[(seg[12] >> 4) * 4:])
    except (IndexError, struct.error):
        pass
    return None


# ------------------------------------------------------------- MAVLink ----
def mav_frames(buf):
    """Genera (version, seq, msgid, payload_len) escaneando el buffer."""
    i, n = 0, len(buf)
    while i < n:
        if buf[i] == 0xFD:                               # MAVLink 2
            if i + 12 > n:
                break
            total = 12 + buf[i + 1] + (13 if buf[i + 2] & 0x01 else 0)
            if i + total > n:
                break
            msgid = buf[i + 7] | buf[i + 8] << 8 | buf[i + 9] << 16
            yield (2, buf[i + 4], msgid, buf[i + 1])
            i += total
        elif buf[i] == 0xFE:                             # MAVLink 1
            if i + 8 > n:
                break
            total = 8 + buf[i + 1]
            if i + total > n:
                break
            yield (1, buf[i + 2], buf[i + 5], buf[i + 1])
            i += total
        else:
            i += 1


# ------------------------------------------------------------- analisis ----
def analyze(path):
    pkts = 0
    t_first = t_last = None
    flows = collections.Counter()
    tcp_streams = collections.defaultdict(bytearray)
    msgids = collections.Counter()
    hqc_events = []                                      # (t_rel, msgid)

    for ts, lt, data in read_pcapng(path):
        pkts += 1
        if ts is not None:
            t_first = ts if t_first is None else t_first
            t_last = ts
        d = decode(lt, data)
        if not d:
            continue
        proto, src, sp, dst, dp, payload = d
        flows[(proto, "%s:%d" % (src, sp), "%s:%d" % (dst, dp))] += 1
        if not payload:
            continue
        if proto == "TCP":
            tcp_streams[(src, sp, dst, dp)] += payload   # el stream se reensambla
            continue
        base = t_first or 0
        for _, _, msgid, _ in mav_frames(payload):       # UDP: datagrama = mensaje
            msgids[msgid] += 1
            if HQC_LO <= msgid <= HQC_HI:
                hqc_events.append((round((ts or 0) - base, 4), msgid))

    for buf in tcp_streams.values():                     # TCP: escanear reensamblado
        for _, _, msgid, _ in mav_frames(buf):
            msgids[msgid] += 1
            if HQC_LO <= msgid <= HQC_HI:
                hqc_events.append((None, msgid))

    dur = (t_last - t_first) if (t_first and t_last) else 0.0
    return dict(pkts=pkts, dur=dur, flows=flows, msgids=msgids, hqc=hqc_events)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    detalle = "--detalle" in sys.argv
    here = os.path.dirname(os.path.abspath(__file__))
    cap = args[0] if args else os.path.normpath(os.path.join(
        here, "..", "..", "firmware-fork", "captures"))

    files = sorted(glob.glob(os.path.join(cap, "*.pcapng")))
    files += sorted(glob.glob(os.path.join(cap, "previous_pcaps", "*.pcapng")))
    if not files:
        print("No hay capturas en %s" % cap)
        return 1

    print("Directorio: %s\n" % cap)
    print("%-44s %6s %8s %6s %5s  %-10s %s" %
          ("captura", "pkts", "dur(s)", "MAV", "HQC", "transporte", "extremo principal"))
    print("-" * 132)

    tot_hqc = collections.Counter()
    for f in files:
        r = analyze(f)
        name = os.path.relpath(f, cap).replace("\\", "/")
        nmav = sum(r["msgids"].values())
        nhqc = sum(1 for _, m in r["hqc"])
        tot_hqc.update(m for _, m in r["hqc"])
        if r["flows"]:
            (proto, a, b), _ = r["flows"].most_common(1)[0]
            extremo = "%s -> %s" % (a, b)
        else:
            proto, extremo = "-", "(sin IPv4)"
        print("%-44s %6d %8.2f %6d %5d  %-10s %s" %
              (name, r["pkts"], r["dur"], nmav, nhqc, proto, extremo))
        if detalle and r["msgids"]:
            top = ", ".join("%d:%d" % (k, v) for k, v in sorted(r["msgids"].items()))
            print("%-44s msgid -> %s" % ("", top))

    print("\n## Mensajes del dialecto HQC, global")
    if tot_hqc:
        for k in sorted(tot_hqc):
            print("   msgid %d: %d" % (k, tot_hqc[k]))
    else:
        print("   ninguno")
    return 0


if __name__ == "__main__":
    sys.exit(main())
