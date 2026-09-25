# -*- coding: utf-8 -*-
"""
Verifica la tabla de estrés de batería (R1..R5) del manuscrito contra las capturas citadas.

Para cada captura extrae: duración, todas las lecturas de SoC con marca de tiempo,
primera y última lectura bien formada, y compara con lo que reporta el paper.

Salida: tabla de trazabilidad en Markdown por stdout.
"""
import os, collections
from scapy.all import PcapNgReader, UDP, Raw
from pymavlink.dialects.v20 import ardupilotmega as m2

CAP = r"D:\Tesis\Carlos_TAES_PQ_MAVLink\02_repo\cdcp2-ardupilot_post_quantum_kem-b402392\captures"

# Lo que reporta el manuscrito (tabla tab:battery_runs)
PAPER = [
    ("R1", "gcs_20251113_180441.pcapng", 18, 222.856, 53, 48, 5, 1.346),
    ("R2", "gcs_20251113_182734.pcapng", 19, 266.554, 75, 71, 4, 0.900),
    ("R3", "gcs_20251113_184155.pcapng", 22, 298.175, 67, 63, 4, 0.805),
    ("R4", "gcs_20251113_190020.pcapng", 23, 363.837, 82, 76, 6, 0.989),
    ("R5", "gcs_20251113_191218.pcapng", 23, 503.046, 73, 67, 6, 0.716),
]


class S:
    def write(self, *a, **k): pass
    def read(self, *a, **k): return b""


def soc_series(path):
    """Devuelve [(t_rel, soc)] de lecturas bien formadas, y la duración total de la captura."""
    mav = m2.MAVLink(S()); mav.robust_parsing = True
    out, ts = [], []
    t0 = None
    with PcapNgReader(path) as r:
        for pkt in r:
            if UDP not in pkt or Raw not in pkt:
                continue
            t = float(pkt.time)
            if t0 is None:
                t0 = t
            ts.append(t)
            for byte in bytes(pkt[Raw].load):
                try:
                    msg = mav.parse_char(bytes([byte]))
                except Exception:
                    continue
                if msg is None:
                    continue
                if msg.get_type() in ("SYS_STATUS", "BATTERY_STATUS"):
                    v = msg.to_dict().get("battery_remaining")
                    if v is not None and v != -1:
                        out.append((round(t - t0, 3), int(v)))
    dur = round(max(ts) - min(ts), 3) if ts else 0.0
    return out, dur


def main():
    print("# Trazabilidad — tabla de estrés de batería (R1..R5)\n")
    print("Cada fila del manuscrito contrastada contra la captura que cita.\n")
    print("| Run | Captura | Dur. paper | Dur. captura | SoC ini paper | SoC ini dato | "
          "SoC fin paper | SoC fin dato | Lecturas | Veredicto |")
    print("|---|---|---|---|---|---|---|---|---|---|")

    for run, cap, nhs, dur_p, s0_p, s1_p, loss_p, rate_p in PAPER:
        path = os.path.join(CAP, cap)
        if not os.path.exists(path):
            print(f"| {run} | `{cap}` | {dur_p} | — | {s0_p} | — | {s1_p} | — | — | "
                  f"**captura ausente** |")
            continue
        series, dur = soc_series(path)
        if not series:
            print(f"| {run} | `{cap}` | {dur_p} | {dur} | {s0_p} | — | {s1_p} | — | 0 | "
                  f"**sin lecturas de SoC** |")
            continue
        s0_d, s1_d = series[0][1], series[-1][1]
        vals = sorted({v for _, v in series})
        ok_ini = (s0_d == s0_p)
        ok_fin = (s1_d == s1_p)
        if ok_ini and ok_fin:
            verd = "trazable"
        elif ok_ini:
            verd = f"**fin no coincide** (dato: {s1_d}; valores vistos: {vals})"
        else:
            verd = f"**no coincide** (valores vistos: {vals})"
        print(f"| {run} | `{cap}` | {dur_p} | {dur} | {s0_p} | {s0_d} | {s1_p} | {s1_d} | "
              f"{len(series)} | {verd} |")

    print("\n## Detalle de las series (t_rel en s, SoC en %)\n")
    for run, cap, *_ in PAPER:
        path = os.path.join(CAP, cap)
        if not os.path.exists(path):
            continue
        series, dur = soc_series(path)
        comp = ", ".join(f"{t}s→{v}%" for t, v in series[:14])
        print(f"- **{run}** (`{cap}`, dur {dur}s, {len(series)} lecturas): {comp}"
              f"{' …' if len(series) > 14 else ''}")


if __name__ == "__main__":
    main()
