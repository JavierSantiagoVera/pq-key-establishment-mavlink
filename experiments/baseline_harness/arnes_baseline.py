#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
arnes_baseline.py -- arnes de medida de linea base (S3 del portatil, M1/M2/M3 de
08_cierre/PLAN_CAMPANA.md #3).

QUE MIDE
  M1  comando -> ACK     : COMMAND_LONG (MAV_CMD_REQUEST_MESSAGE) a 10 Hz, emparejado
                           con su COMMAND_ACK.
  M2  RTT del enlace     : TIMESYNC a 10 Hz. El FC devuelve el mismo ts1 que mandamos
                           en tc1; RTT = ahora - ts1.
  M3  jitter de telemetria: ATTITUDE a 50 Hz (pedido con MAV_CMD_SET_MESSAGE_INTERVAL),
                           tiempo entre llegadas en este proceso.

QUE ES ESTO Y QUE NO ES
  Es el ENSAYO EN SECO que pide 08_cierre/HANDOFF_PORTATIL.md (S3) y
  08_cierre/PLAN_CAMPANA.md (E6/T7): probar que el arnes funciona y que las cifras
  salen de un archivo y un comando, antes de gastar bateria del dron.
  NO ES una medida de C5: corre contra SITL, que compila para el host con reloj
  simulado, asi que el jitter que salga aqui es JITTER DE LINUX, no de un
  autopiloto real (ver NOTAS_ONBOARDING.txt #7, "la trampa de la tarea 3"). Ninguna
  cifra de esta corrida debe citarse en el articulo como resultado de C5.

SALIDA
  Tres .jsonl (uno por metrica, una linea por muestra) en --out-dir, y un resumen
  p50/p95/p99 impreso y volcado a resumen.json en la misma carpeta. Cada numero del
  resumen se recalcula leyendo esos .jsonl: se puede reproducir con
  analizar_resumen.py sin volver a correr contra el vehiculo.

USO
  source ~/venv-ardupilot/bin/activate.fish
  python3 arnes_baseline.py --host tcp:127.0.0.1:5762 --duration 20 \
      --out-dir salidas/$(date +%Y%m%d_%H%M%S)_sitl
"""
import argparse
import json
import os
import sys
import time

from pymavlink import mavutil

EPOCH_OFFSET = 1420070400  # 1/1/2015, el mismo que usa GCS_Signing.cpp


def activar_firma_gcs(m):
    """Hace que ESTE cliente firme sus mensajes salientes (rol de la GCS que
    experiments/signing_policy/HALLAZGO_firma_no_exigida.md encontro que hoy no
    firma nunca). Manda SETUP_SIGNING (todavia sin firma activa, se acepta igual) y
    configura la firma local. No verifica la firma de lo que manda el FC -- no es el
    objetivo de este arnes, que es medir M1-M3, no auditar la firma del FC (eso ya lo
    hace firma_en_sitl.py)."""
    secret_key = os.urandom(32)
    ts0 = int((time.time() - EPOCH_OFFSET) * 100 * 1000)
    m.mav.setup_signing_send(m.target_system, m.target_component, list(secret_key), ts0)
    time.sleep(1.0)
    m.setup_signing(secret_key, sign_outgoing=True,
                     allow_unsigned_callback=lambda *a: True,
                     initial_timestamp=ts0 + 10_000_000_000)
    return secret_key, ts0


def ahora_ns():
    return time.monotonic_ns()


def percentil(muestras, p):
    if not muestras:
        return None
    s = sorted(muestras)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


def resumen_de(muestras_ms, etiqueta):
    return {
        "metrica": etiqueta,
        "n": len(muestras_ms),
        "p50_ms": percentil(muestras_ms, 50),
        "p95_ms": percentil(muestras_ms, 95),
        "p99_ms": percentil(muestras_ms, 99),
        "max_ms": max(muestras_ms) if muestras_ms else None,
    }


def medir_m1_comando_ack(m, duracion_s, tasa_hz, archivo):
    """COMMAND_LONG(MAV_CMD_REQUEST_MESSAGE, HEARTBEAT) a tasa_hz; empareja con COMMAND_ACK."""
    periodo = 1.0 / tasa_hz
    n_muestras = int(duracion_s * tasa_hz)
    latencias_ms = []
    perdidos = 0

    with open(archivo, "w", encoding="utf-8") as f:
        for i in range(n_muestras):
            t0 = ahora_ns()
            m.mav.command_long_send(
                m.target_system, m.target_component,
                mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, i % 256,
                mavutil.mavlink.MAVLINK_MSG_ID_HEARTBEAT, 0, 0, 0, 0, 0, 0,
            )

            recibido = False
            while (ahora_ns() - t0) < int(0.5 * periodo * 1e9):
                msg = m.recv_match(type="COMMAND_ACK", blocking=False)
                if msg is not None:
                    t1 = ahora_ns()
                    lat_ms = (t1 - t0) / 1e6
                    latencias_ms.append(lat_ms)
                    f.write(json.dumps({"i": i, "t0_ns": t0, "lat_ms": lat_ms,
                                        "result": msg.result}) + "\n")
                    recibido = True
                    break
            if not recibido:
                perdidos += 1
                f.write(json.dumps({"i": i, "t0_ns": t0, "lat_ms": None}) + "\n")

            dt = periodo - (ahora_ns() - t0) / 1e9
            if dt > 0:
                time.sleep(dt)

    return latencias_ms, perdidos, n_muestras


def medir_m2_timesync(m, duracion_s, tasa_hz, archivo):
    """TIMESYNC a tasa_hz; el FC responde con ts1 = el mismo que mandamos."""
    periodo = 1.0 / tasa_hz
    n_muestras = int(duracion_s * tasa_hz)
    rtts_ms = []
    perdidos = 0

    with open(archivo, "w", encoding="utf-8") as f:
        for i in range(n_muestras):
            ts1 = ahora_ns()
            m.mav.timesync_send(0, ts1)

            recibido = False
            while (ahora_ns() - ts1) < int(0.5 * periodo * 1e9):
                msg = m.recv_match(type="TIMESYNC", blocking=False)
                if msg is not None and msg.ts1 == ts1:
                    t1 = ahora_ns()
                    rtt_ms = (t1 - ts1) / 1e6
                    rtts_ms.append(rtt_ms)
                    f.write(json.dumps({"i": i, "ts1_ns": ts1, "rtt_ms": rtt_ms}) + "\n")
                    recibido = True
                    break
            if not recibido:
                perdidos += 1
                f.write(json.dumps({"i": i, "ts1_ns": ts1, "rtt_ms": None}) + "\n")

            dt = periodo - (ahora_ns() - ts1) / 1e9
            if dt > 0:
                time.sleep(dt)

    return rtts_ms, perdidos, n_muestras


def medir_m3_jitter_attitude(m, duracion_s, tasa_hz_pedida, archivo):
    """Pide ATTITUDE a tasa_hz_pedida y mide el intervalo entre llegadas."""
    intervalo_us = int(1e6 / tasa_hz_pedida)
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
        mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE, intervalo_us, 0, 0, 0, 0, 0,
    )
    m.recv_match(type="COMMAND_ACK", blocking=True, timeout=2)

    intervalos_ms = []
    t_anterior = None
    t_fin = time.monotonic() + duracion_s

    with open(archivo, "w", encoding="utf-8") as f:
        while time.monotonic() < t_fin:
            msg = m.recv_match(type="ATTITUDE", blocking=True, timeout=1)
            if msg is None:
                continue
            t_llegada = ahora_ns()
            if t_anterior is not None:
                dt_ms = (t_llegada - t_anterior) / 1e6
                intervalos_ms.append(dt_ms)
                f.write(json.dumps({"t_ns": t_llegada, "dt_ms": dt_ms}) + "\n")
            t_anterior = t_llegada

    return intervalos_ms


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="tcp:127.0.0.1:5762",
                     help="conexion mavlink (default: puerto secundario de SITL, no compite "
                          "con la consola de MAVProxy en 5760)")
    ap.add_argument("--duration", type=float, default=20.0, help="segundos por metrica")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--firmar", action="store_true",
                     help="firma los mensajes salientes (rol de la GCS que hoy no firma, "
                          "ver HALLAZGO_firma_no_exigida.md). Requiere que el FC acepte "
                          "SETUP_SIGNING (no armado).")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    print("Conectando a %s ..." % args.host)
    m = mavutil.mavlink_connection(args.host, source_system=250)
    m.wait_heartbeat(timeout=15)
    print("Heartbeat recibido. target_system=%d target_component=%d" %
          (m.target_system, m.target_component))
    print("AVISO: esta corrida es sobre SITL. El jitter medido es jitter de Linux,")
    print("       NO representa el autopiloto real. No citar en el articulo.\n")

    secret_key = None
    if args.firmar:
        print("Activando firma del lado GCS (rol que hoy no firma nunca) ...")
        secret_key, _ = activar_firma_gcs(m)
        print("Firma activa. Los COMMAND_LONG/TIMESYNC/SET_MESSAGE_INTERVAL salientes "
              "van firmados.\n")

    resultados = []

    print("M1 -- comando -> ACK, 10 Hz, %.0f s" % args.duration)
    lat, perdidos, n = medir_m1_comando_ack(
        m, args.duration, 10.0, os.path.join(args.out_dir, "m1_comando_ack.jsonl"))
    r = resumen_de(lat, "M1_comando_ack_ms")
    r["perdidos"] = perdidos
    r["enviados"] = n
    resultados.append(r)

    print("M2 -- TIMESYNC, 10 Hz, %.0f s" % args.duration)
    rtt, perdidos, n = medir_m2_timesync(
        m, args.duration, 10.0, os.path.join(args.out_dir, "m2_timesync.jsonl"))
    r = resumen_de(rtt, "M2_timesync_rtt_ms")
    r["perdidos"] = perdidos
    r["enviados"] = n
    resultados.append(r)

    print("M3 -- ATTITUDE a 50 Hz pedidos, jitter de llegada, %.0f s" % args.duration)
    intervalos = medir_m3_jitter_attitude(
        m, args.duration, 50.0, os.path.join(args.out_dir, "m3_attitude_jitter.jsonl"))
    r = resumen_de(intervalos, "M3_attitude_intervalo_ms")
    if r["p99_ms"] is not None:
        r["p99_menos_20ms"] = r["p99_ms"] - 20.0
    r["huecos_mayores_100ms"] = sum(1 for x in intervalos if x > 100.0)
    resultados.append(r)

    resumen_path = os.path.join(args.out_dir, "resumen.json")
    with open(resumen_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 78)
    print(" RESUMEN (SITL -- ensayo en seco, NO es medida de C5)")
    print("=" * 78)
    for r in resultados:
        print(" %s" % r["metrica"])
        for k, v in r.items():
            if k == "metrica":
                continue
            print("   %-22s: %s" % (k, v))
    print("\nDatos crudos y resumen en: %s" % args.out_dir)

    if args.firmar:
        # Desactivar FIRMADA (si el FC tiene el parche de canal 0, un mensaje sin
        # firmar por cualquier canal se descarta -- ver parche_canal0.patch #11 de
        # HALLAZGO_firma_no_exigida.md). Sin esto, la firma queda activa para la
        # proxima corrida sin --firmar y se ve como "todo se perdio".
        m.mav.setup_signing_send(m.target_system, m.target_component, [0] * 32, 0)
        time.sleep(0.5)
        m.mav.signing.sign_outgoing = False
        print("Firma del lado GCS desactivada (limpieza).")


if __name__ == "__main__":
    sys.exit(main())
