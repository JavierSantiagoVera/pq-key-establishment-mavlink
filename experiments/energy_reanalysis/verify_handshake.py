# -*- coding: utf-8 -*-
"""
Verifica las cifras de handshake del manuscrito contra las capturas.

El diálogo HQC (msgid 61000-61008) no está en pymavlink, así que se parsea el framing
MAVLink v2 a mano: 0xFD | len | incompat | compat | seq | sysid | compid | msgid(3B) | payload | crc(2B)
(+13B de firma si incompat & 0x01).

Mide: nº de handshakes (por HQC_HELLO), completados (por STATUS final), y duración
HELLO->STATUS de cada sesión.
"""
import os, glob, struct, collections
from scapy.all import PcapNgReader, UDP, Raw

CAP = r"D:\Tesis\Carlos_TAES_PQ_MAVLink\02_repo\cdcp2-ardupilot_post_quantum_kem-b402392\captures"


def frames(path):
    """Genera (t_rel, msgid, payload_len) de cada frame MAVLink v2 de la captura."""
    t0 = None
    with PcapNgReader(path) as r:
        for pkt in r:
            if UDP not in pkt or Raw not in pkt:
                continue
            t = float(pkt.time)
            if t0 is None:
                t0 = t
            b = bytes(pkt[Raw].load)
            i = 0
            while i < len(b):
                if b[i] != 0xFD:
                    i += 1
                    continue
                if i + 10 > len(b):
                    break
                plen = b[i + 1]
                incompat = b[i + 2]
                msgid = b[i + 7] | (b[i + 8] << 8) | (b[i + 9] << 16)
                total = 12 + plen + (13 if (incompat & 0x01) else 0)
                yield (round(t - t0, 4), msgid, plen)
                i += total if total > 0 else 1


def analyze(path):
    ids = collections.Counter()
    hqc_events = []          # (t, msgid) solo del rango HQC
    for t, msgid, plen in frames(path):
        ids[msgid] += 1
        if 61000 <= msgid <= 61008:
            hqc_events.append((t, msgid))
    return ids, hqc_events


def sessions(hqc_events, hello_id, status_id):
    """Agrupa eventos en sesiones: de cada HELLO al siguiente STATUS."""
    out = []
    open_t = None
    for t, mid in hqc_events:
        if mid == hello_id:
            open_t = t
        elif mid == status_id and open_t is not None:
            out.append((open_t, t, round(t - open_t, 4)))
            open_t = None
    return out


def main():
    pats = ["gcs_20251113_18*.pcapng", "gcs_20251113_19*.pcapng",
            "gcs_20251113_1[34]*.pcapng"]
    files = []
    for p in pats:
        files.extend(sorted(glob.glob(os.path.join(CAP, p))))

    all_ids = collections.Counter()
    print("## IDs del diálogo HQC encontrados por captura\n")
    print(f"{'captura':40} {'frames':>7} {'HQC msgs':>9}  distribución de msgid HQC")
    print("-" * 110)
    per_file = {}
    for f in files:
        ids, ev = analyze(f)
        all_ids.update(ids)
        hqc = {k: v for k, v in ids.items() if 61000 <= k <= 61008}
        per_file[f] = (ids, ev, hqc)
        tot = sum(ids.values())
        dist = ", ".join(f"{k}:{v}" for k, v in sorted(hqc.items()))
        print(f"{os.path.basename(f):40} {tot:7d} {sum(hqc.values()):9d}  {dist}")

    hqc_global = {k: v for k, v in all_ids.items() if 61000 <= k <= 61008}
    if not hqc_global:
        print("\nNo se encontró ningún mensaje en el rango 61000-61008.")
        return
    print("\n## Global\n")
    for k in sorted(hqc_global):
        print(f"  msgid {k}: {hqc_global[k]}")

    lo, hi = min(hqc_global), max(hqc_global)
    print(f"\nHipótesis: {lo} = inicio de handshake (HELLO), {hi} = estado final (STATUS).\n")
    print("## Sesiones detectadas por captura\n")
    print(f"{'captura':40} {'sesiones':>9} {'media(s)':>9} {'p50':>8} {'min':>8} {'max':>8}")
    print("-" * 92)
    tot_s = []
    for f, (ids, ev, hqc) in per_file.items():
        s = sessions(ev, lo, hi)
        if not s:
            print(f"{os.path.basename(f):40} {0:9d}")
            continue
        durs = sorted(d for _, _, d in s)
        tot_s.extend(durs)
        mean = sum(durs) / len(durs)
        p50 = durs[len(durs) // 2]
        print(f"{os.path.basename(f):40} {len(durs):9d} {mean:9.4f} {p50:8.4f} "
              f"{durs[0]:8.4f} {durs[-1]:8.4f}")
    if tot_s:
        tot_s.sort()
        n = len(tot_s)
        print(f"\nTOTAL: {n} sesiones | media {sum(tot_s)/n:.4f} s | "
              f"p50 {tot_s[n//2]:.4f} s | p95 {tot_s[int(n*0.95)-1]:.4f} s | "
              f"min {tot_s[0]:.4f} | max {tot_s[-1]:.4f}")
        print("\nComparar con el paper: 96 sesiones | media 0.624 | p50 0.611 | p95 0.632 | "
              "min 0.585 | max 1.629")


if __name__ == "__main__":
    main()
