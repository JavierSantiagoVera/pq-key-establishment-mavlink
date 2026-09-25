#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B4_status_field.py -- decodifica el CAMPO de los 100 mensajes HQC_STATUS (61006) de
R1-R5, en vez de solo contarlos (que es lo que hacia extraer_sesiones.py hasta ahora).

QUE PREGUNTA RESPONDE
  08_cierre/README.md #3.6 y B4_RESULTADOS_firma.md #4 encontraron que tres senales
  independientes convergen en 100 (rafagas contadas, mensajes 61006, activacion de
  firma), pero ninguna explica el 96 del articulo (100 intentos / 96 exitos). Este
  script mira DENTRO del payload de esos 100 mensajes -- session_id, value, status,
  detail -- en vez de solo contarlos, para ver si el status distingue exitos de
  fallos.

METODO
  mavlink_msg_hqc_status_send(ch, session_id, value, status, detail) firma el orden
  de LLAMADA, no el orden en el cable: MAVLink 2 reordena los campos del payload por
  tamano decreciente (session_id u64, value u32, status u8, detail u8) y ADEMAS
  recorta los bytes CERO finales del payload (ahorro de ancho de banda). Eso significa
  que un STATUS con value=0, status=0, detail=0 llega en el cable como 8 B (solo
  session_id) -- exactamente lo que se ve en las 5 capturas R1-R5.

RESULTADO (2026-09-17): ver B4_status_field.md.

Uso:
    py -3 experiments/nonce_collision/B4_status_field.py
"""
import os
import sys
import glob
import collections

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_AQUI, "..", "energy_reanalysis"))
from inventario_capturas import read_pcapng, decode  # noqa: E402

R1R5 = ["fc_20251113_180441.pcapng", "fc_20251113_182734.pcapng",
        "fc_20251113_184155.pcapng", "fc_20251113_190020.pcapng",
        "fc_20251113_191218.pcapng"]


def mav_frames_con_payload(buf):
    """Igual que inventario_capturas.mav_frames pero devuelve el payload completo,
    no solo su longitud -- hace falta para leer session_id/value/status/detail."""
    i, n = 0, len(buf)
    while i < n:
        if buf[i] == 0xFD:
            if i + 12 > n:
                break
            ln = buf[i + 1]
            firmada = bool(buf[i + 2] & 0x01)
            total = 12 + ln + (13 if firmada else 0)
            if i + total > n:
                break
            msgid = buf[i + 7] | buf[i + 8] << 8 | buf[i + 9] << 16
            yield msgid, bytes(buf[i + 10:i + 10 + ln])
            i += total
        else:
            i += 1


def status_de(pl):
    """Decodifica un payload de HQC_STATUS, con el recorte de ceros de MAVLink 2
    deshecho: los bytes que faltan respecto a 14 B se rellenan con 0."""
    pl14 = pl + b"\x00" * (14 - len(pl))
    session_id = int.from_bytes(pl14[0:8], "little")
    value = int.from_bytes(pl14[8:12], "little")
    status = pl14[12]
    detail = pl14[13]
    return session_id, value, status, detail


def main():
    cap_dir = os.path.normpath(os.path.join(
        _AQUI, "..", "..", "firmware-fork", "captures"))

    print("=" * 84)
    print(" HQC_STATUS (61006) decodificado, R1-R5")
    print("=" * 84)

    todos = []
    for fn in R1R5:
        f = os.path.join(cap_dir, fn)
        n_este = 0
        for ts, lt, data in read_pcapng(f):
            d = decode(lt, data)
            if not d:
                continue
            proto, src, sp, dst, dp, payload = d
            if not payload or proto == "TCP":
                continue
            for msgid, pl in mav_frames_con_payload(payload):
                if msgid == 61006:
                    todos.append((fn, status_de(pl)))
                    n_este += 1
        print("  %-32s %d mensajes HQC_STATUS" % (fn, n_este))

    print("\nTotal: %d (esperado: 100, de 18+19+21+22+20)" % len(todos))

    valores = collections.Counter((v, s, d) for _, (_, v, s, d) in todos)
    print("\nDistribucion de (value, status, detail) tras deshacer el recorte de ceros:")
    for (v, s, d), n in valores.most_common():
        print("   value=%-4d status=%-4d detail=%-4d  -> %d de %d mensajes"
              % (v, s, d, n, len(todos)))

    sids = [sid for _, (sid, _, _, _) in todos]
    print("\nsession_id distintos: %d de %d" % (len(set(sids)), len(sids)))

    print("\n" + "=" * 84)
    if len(valores) == 1 and len(set(sids)) == len(sids):
        (v, s, d), n = valores.most_common(1)[0]
        print(" CONCLUSION: las 100 sesiones que completan el handshake en R1-R5 reportan")
        print(" EL MISMO (value=%d, status=%d, detail=%d) -- CERO variacion. El campo de" % (v, s, d))
        print(" estado de HQC_STATUS NO distingue exitos de fallos en este conjunto de datos:")
        print(" el 96/100 del articulo, si es real, no se ve por esta via. O el fallo ocurre")
        print(" DESPUES de este STATUS (p.ej. en la decapsulacion del lado GCS, que es donde")
        print(" el articulo situa esa validacion, l.897/1112 - un fallo ahi no le llega nunca")
        print(" al FC ni se ve en estas capturas).")
    else:
        print(" CONCLUSION: SI hay variacion -- revisar los casos distintos de arriba,")
        print(" pueden ser la pista que faltaba.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
