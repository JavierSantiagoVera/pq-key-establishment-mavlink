# -*- coding: utf-8 -*-
"""
Extrae telemetría de batería de las capturas pcapng del experimento de Carlos.

Objetivo: determinar QUÉ campos de batería están realmente presentes, para decidir
con evidencia si el resultado energético puede rescatarse (coulomb counting con
voltaje/corriente) o si solo existe el SoC cuantizado al 1 % (no rescatable).

Salida: CSV por captura + resumen de campos disponibles.
"""
import sys, os, glob, csv
from collections import defaultdict

from scapy.all import PcapNgReader, UDP, Raw
from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega as mavlink2


CAPTURES = r"D:\Tesis\Carlos_TAES_PQ_MAVLink\02_repo\cdcp2-ardupilot_post_quantum_kem-b402392\captures"
OUTDIR = r"D:\Tesis\Carlos_TAES_PQ_MAVLink\04_experiments\energy_reanalysis"


class Sink:
    """pymavlink necesita un 'file' para MAVLink(); solo usamos parse_char."""
    def write(self, *a, **k):
        pass
    def read(self, *a, **k):
        return b""


def parse_capture(path):
    """Devuelve (rows, field_presence) para una captura."""
    mav = mavlink2.MAVLink(Sink())
    mav.robust_parsing = True
    rows = []
    presence = defaultdict(int)
    msgcount = defaultdict(int)
    t0 = None

    try:
        reader = PcapNgReader(path)
    except Exception as e:
        return None, None, f"no se pudo abrir: {e}"

    with reader:
        for pkt in reader:
            if UDP not in pkt or Raw not in pkt:
                continue
            ts = float(pkt.time)
            if t0 is None:
                t0 = ts
            payload = bytes(pkt[Raw].load)
            try:
                msgs = mav.parse_buffer(payload)
            except Exception:
                msgs = None
            if not msgs:
                continue
            for m in msgs:
                mt = m.get_type()
                msgcount[mt] += 1
                if mt == "SYS_STATUS":
                    d = m.to_dict()
                    row = {
                        "t_rel": round(ts - t0, 3),
                        "msg": "SYS_STATUS",
                        "voltage_mV": d.get("voltage_battery"),
                        "current_cA": d.get("current_battery"),
                        "soc_pct": d.get("battery_remaining"),
                    }
                    rows.append(row)
                    for k in ("voltage_mV", "current_cA", "soc_pct"):
                        if row[k] not in (None, -1, 65535):
                            presence[k] += 1
                elif mt == "BATTERY_STATUS":
                    d = m.to_dict()
                    volts = d.get("voltages") or []
                    v0 = volts[0] if volts else None
                    row = {
                        "t_rel": round(ts - t0, 3),
                        "msg": "BATTERY_STATUS",
                        "voltage_mV": v0 if v0 not in (65535,) else None,
                        "current_cA": d.get("current_battery"),
                        "soc_pct": d.get("battery_remaining"),
                    }
                    rows.append(row)
                    for k in ("voltage_mV", "current_cA", "soc_pct"):
                        if row[k] not in (None, -1, 65535):
                            presence[k] += 1
    return rows, (presence, msgcount, t0), None


def main():
    pats = sys.argv[1:] or ["gcs_clear*", "gcs_aesctr*", "gcs_chacha*"]
    files = []
    for p in pats:
        files.extend(sorted(glob.glob(os.path.join(CAPTURES, p + ".pcapng"))))
    if not files:
        print("No se encontraron capturas para:", pats)
        return 1

    print(f"{'captura':45} {'muestras':>9} {'V ok':>6} {'I ok':>6} {'SoC ok':>7}  {'dur(s)':>8}")
    print("-" * 92)
    for f in files:
        rows, meta, err = parse_capture(f)
        base = os.path.basename(f)
        if err:
            print(f"{base:45} ERROR: {err}")
            continue
        presence, msgcount, _ = meta
        dur = rows[-1]["t_rel"] if rows else 0
        print(f"{base:45} {len(rows):9d} {presence.get('voltage_mV',0):6d} "
              f"{presence.get('current_cA',0):6d} {presence.get('soc_pct',0):7d} {dur:8.1f}")

        out = os.path.join(OUTDIR, base.replace(".pcapng", "_battery.csv"))
        if rows:
            with open(out, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=["t_rel", "msg", "voltage_mV",
                                                   "current_cA", "soc_pct"])
                w.writeheader()
                w.writerows(rows)
        # valores distintos de SoC (para ver la cuantización real)
        socs = sorted({r["soc_pct"] for r in rows if r["soc_pct"] not in (None, -1)})
        print(f"{'':45} SoC distintos: {socs[:12]}{' ...' if len(socs) > 12 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
