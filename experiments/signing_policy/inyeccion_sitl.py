#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inyeccion_sitl.py -- I1, I3 e I4 de 08_cierre/PLAN_CAMPANA.md #4.2, contra SITL en vez
del Bebop (ese plan las penso para hardware real y el proxy, que no existen). Usa
directamente la firma MAVLink 2 -- ya probada en firma_en_sitl.py -- porque no hace
falta el proxy/cifrador para probar el mecanismo de rechazo en si.

QUE SI Y QUE NO
  I1 (comando sin firma) ya se midio en HALLAZGO_firma_no_exigida.md #11-12 -- aqui se
  referencia, no se repite. I3 (replay de una trama firmada) e I4 (voltear un bit de una
  trama firmada) son nuevas: se fabrican los bytes exactos de la trama a mano.
  I2 (mismo ataque a todos los puertos UDP) e I5 (reflejar una trama del FC hacia el FC)
  no se hacen: I2 no aporta nada nuevo sobre I1 en esta topologia de un solo puerto; I5
  necesita el proxy de dos patas. I6 (HELLO sin autenticar con sesion activa) necesita el
  estado del handshake KEMTLS (GCS_KEMTLS.cpp), que no esta en SITL -- solo en el fork.

  Sin control positivo en "A" (sin firma) porque eso ya lo hizo firma_en_sitl.py -- este
  script asume que la firma YA esta activa y exigida (canal no-0, SITL stock, sin el
  parche de canal 0: ya se sabe que ese canal exige firma sin tocar nada).

Compilar y correr: ver README.md de esta carpeta ("Inyeccion en SITL").
"""
import os
import sys
import time
import struct

from pymavlink import mavutil
from pymavlink.generator.mavcrc import x25crc

EPOCH_OFFSET = 1420070400


def ts_ahora():
    return int((time.time() - EPOCH_OFFSET) * 100 * 1000)


def esperar_ack(m, timeout_s=1.5):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        msg = m.recv_match(type="COMMAND_ACK", blocking=False)
        if msg is not None:
            return msg
        time.sleep(0.02)
    return None


def recrc(buf_sin_crc, crc_extra):
    """CRC X.25 de MAVLink 2 sobre [len..payload] + crc_extra del mensaje."""
    c = x25crc(buf_sin_crc)
    c.accumulate(bytes([crc_extra]))
    return c.crc & 0xFFFF


def main():
    ap_host = sys.argv[1] if len(sys.argv) > 1 else "tcp:127.0.0.1:5762"
    if ap_host.endswith(":5760"):
        print("ABORTA: no usar 5760 (consola). Usar un canal que ya exija firma, p.ej. 5762.")
        return 1

    print("Conectando a %s ..." % ap_host)
    m = mavutil.mavlink_connection(ap_host, source_system=250)
    hb = m.wait_heartbeat(timeout=15)
    tsys, tcomp = hb.get_srcSystem(), hb.get_srcComponent()
    print("Heartbeat OK. target=%d/%d" % (tsys, tcomp))

    secret_key = os.urandom(32)
    ts0 = ts_ahora()
    print("\n[setup] SETUP_SIGNING + firma local del lado GCS ...")
    m.mav.setup_signing_send(tsys, tcomp, list(secret_key), ts0)
    time.sleep(1.0)
    m.setup_signing(secret_key, sign_outgoing=True,
                     allow_unsigned_callback=lambda *a: True,
                     initial_timestamp=ts0 + 10_000_000_000)

    fallos = 0

    def chk(nombre, cond):
        nonlocal fallos
        print("  [%s] %s" % ("OK  " if cond else "FALLA", nombre))
        if not cond:
            fallos += 1

    # --------------------------------------------------------- trama de referencia
    msg_ref = m.mav.command_long_encode(
        tsys, tcomp, mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 100,
        mavutil.mavlink.MAVLINK_MSG_ID_HEARTBEAT, 0, 0, 0, 0, 0, 0)
    frame_a = msg_ref.pack(m.mav)  # firmada de verdad, referencia (control: SI se acepta)
    m.write(frame_a)
    ack0 = esperar_ack(m)
    chk("control: trama de referencia firmada SI se acepta", ack0 is not None)

    # -------------------------------------------------------------- I3: replay exacto
    print("\nI3 -- repetir la MISMA trama firmada (bytes identicos, mismo timestamp)")
    m.write(frame_a)
    ack_i3 = esperar_ack(m)
    chk("0 ACK -- el replay exacto se rechaza (misma firma, mismo timestamp)", ack_i3 is None)

    # --------------------------------------------------- I4: bit-flip con firma vieja
    print("\nI4 -- voltear un bit del payload, CRC recalculado, firma VIEJA (de otra trama)")
    msg_mod = m.mav.command_long_encode(
        tsys, tcomp, mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 101,  # confirmation distinta
        mavutil.mavlink.MAVLINK_MSG_ID_HEARTBEAT, 0, 0, 0, 0, 0, 0)
    m.mav.signing.sign_outgoing = False
    frame_b_sin_firma = msg_mod.pack(m.mav)  # CRC correcto para ESTE payload, sin firmar
    m.mav.signing.sign_outgoing = True

    ln = frame_b_sin_firma[1]
    header_y_payload = frame_b_sin_firma[:10 + ln]          # hasta el final del payload
    crc_val = recrc(header_y_payload[1:], msg_mod.crc_extra)  # X.25 arranca en el byte de longitud
    frame_falsificada = bytearray(header_y_payload)
    frame_falsificada[2] |= 0x01                             # marcar como "firmada"
    frame_falsificada += struct.pack("<H", crc_val)
    frame_falsificada += frame_a[-13:]                       # firma VIEJA, de otra trama

    m.write(bytes(frame_falsificada))
    ack_i4 = esperar_ack(m)
    chk("0 ACK -- CRC valido pero firma de otra trama, se rechaza", ack_i4 is None)

    # ------------------------------------------------------- control: firmada bien
    print("\nControl -- una trama nueva, firmada correctamente, SI se acepta")
    msg_ok = m.mav.command_long_encode(
        tsys, tcomp, mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 102,
        mavutil.mavlink.MAVLINK_MSG_ID_HEARTBEAT, 0, 0, 0, 0, 0, 0)
    m.write(msg_ok.pack(m.mav))
    ack_ok = esperar_ack(m)
    chk("una trama nueva y bien firmada SI se acepta (I3/I4 no dejaron el canal roto)",
        ack_ok is not None)

    print("\n[limpieza] desactivando firma por el canal 0 (5760, nunca la exige) ...")
    try:
        m0 = mavutil.mavlink_connection("tcp:127.0.0.1:5760", source_system=251)
        m0.wait_heartbeat(timeout=10)
        m0.mav.setup_signing_send(m0.target_system, m0.target_component, [0] * 32, 0)
        time.sleep(1.0)
        m0.close()
        print("  OK")
    except Exception as e:
        print("  AVISO: no se pudo limpiar por canal 0 (%s)" % e)
    m.close()

    print("\n%s\n" % ("TODO CORRECTO" if fallos == 0 else "HAY FALLOS"))
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
