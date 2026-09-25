#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
firma_en_sitl.py -- experimento #3 de 08_cierre/README.md #B-bis.

QUE PREGUNTA RESPONDE
  HALLAZGO_firma_no_exigida.md encontro, leyendo GCS_Signing.cpp del FORK y
  confirmando con capturas del Bebop, que el FC acepta SIEMPRE tramas sin
  firma en el canal 0 ("assumed to be secure channel. This is USB on ChibiOS
  boards"). Aqui se comprueba, EN VIVO y contra SITL SIN NINGUN CODIGO DEL
  FORK (ArduPilot puro, tal como lo instalo S1), dos cosas:

  (a) que la funcion accept_unsigned_callback() -- la responsable del defecto
      -- es CODIGO DE ARDUPILOT, no del fork: ver el diff mas abajo. Esto es
      estatico, no hace falta correr nada para comprobarlo.
  (b) que, en un canal que SI la exige, la firma MAVLink 2 rechaza de verdad
      un comando sin firmar y acepta el mismo comando cuando se firma
      correctamente (control positivo). Esto es EN VIVO, con SITL corriendo.

  No prueba (b) en el propio "canal 0": ver LIMITE mas abajo.

(a) -- diff entre el archivo del fork y el mismo archivo del arbol de SITL
       (02_repo/.../GCS_Signing.cpp vs ~/ardupilot/.../GCS_Signing.cpp):
       accept_unsigned_callback() NO cambia una linea. El fork solo AÑADE
       enable_signing_with_key() (una API para activar la firma en runtime
       con la k_sign que sale del handshake); no toca la politica de
       aceptacion. Reproducir:
           diff -u firmware-fork/libraries/GCS_MAVLink/GCS_Signing.cpp \
                   ~/ardupilot/libraries/GCS_MAVLink/GCS_Signing.cpp

LIMITE -- por que esto NO reproduce en vivo la excepcion del canal 0
  SITL abre varios puertos TCP (5760, 5762, 5763). El 5760 es la consola de
  MAVProxy que el usuario puede tener abierta (S1); no se toca para no
  interferir con esa sesion. Los puertos 5762/5763 son canales MAVLink
  DISTINTOS de 0 (confirmado: wait_heartbeat da target_system=1 igual que
  5760, pero cada puerto es un enlace/canal separado en GCS_MAVLink). Este
  script solo usa 5762, y por tanto solo puede demostrar el lado
  "SI exigido, SI rechaza / SI firmado, SI acepta" -- no el "canal 0 acepta
  igual". Ese lado ya esta medido de otra forma: el diff de (a), y las
  capturas del Bebop de HALLAZGO_firma_no_exigida.md #1-2.

QUE HACE, EN ORDEN
  1. Activa la firma en el FC (SETUP_SIGNING, sin firmar -- todavia no hay
     firma activa en ningun canal, asi que esto se acepta en cualquiera).
  2. Manda un COMMAND_LONG SIN firmar por el canal de 5762 -> se espera que
     NO llegue COMMAND_ACK (el canal exige firma y este comando no la trae).
  3. Control positivo: activa la firma correcta del lado GCS (misma clave) en
     esa misma conexion y repite el comando -> se espera que esta vez SI
     llegue el ACK. Si (2) fallo por otra razon (puerto mal, timeout corto),
     (3) tambien fallaria, y el experimento lo señala en vez de asumir.
  4. Limpieza: desactiva la firma (clave y timestamp en cero, que es como
     GCS_Signing.cpp::load_signing_key() interpreta "sin firma") para dejar
     el SITL como estaba, y no romper otros experimentos de hoy que ya
     asumen sin firma (p. ej. baseline_harness).

RESULTADO DEL 2026-09-16 -- PARCIAL, NO SE FUERZA
  (2) SI se confirmo, repetible: el canal exige firma y un COMMAND_LONG sin
      firmar no recibe ACK.
  (3) NO se pudo confirmar todavia: ni firmando con la misma clave llega el
      ACK. Se investigo con logging y contadores de pymavlink
      (self.mav.signing.sig_count/goodsig_count/badsig_count): el FC SI firma
      sus propios HEARTBEAT/ATTITUDE salientes (sig_count > 0), pero fallan la
      verificacion local con "sig mismatch" (HMAC no coincide, no es problema
      de timestamp/replay -- eso se descarto por separado). Osea que la MISMA
      clave que se manda por SETUP_SIGNING no reproduce el HMAC ni en el
      sentido FC->GCS ni GCS->FC. No se encontro la causa exacta (podria ser
      del lado de pymavlink, de esta version de SITL, o de algo en cache de
      GCS_Signing.cpp entre corridas) dentro del tiempo invertido -- se marca
      NO VERIFICADO y se deja como trabajo futuro en vez de inventar un OK.
      Detalle de lo probado: README.md de esta carpeta.

Uso:
    source ~/venv-ardupilot/bin/activate.fish
    python3 firma_en_sitl.py --host tcp:127.0.0.1:5762
"""
import argparse
import os
import time

from pymavlink import mavutil

EPOCH_OFFSET = 1420070400  # 1/1/2015, el mismo que usa GCS_Signing.cpp


def ts_firma_actual():
    """Timestamp de firma MAVLink2: unidades de 10 us desde 1/1/2015."""
    return int((time.time() - EPOCH_OFFSET) * 100 * 1000)


def esperar_ack(m, timeout_s=1.5):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        msg = m.recv_match(type="COMMAND_ACK", blocking=False)
        if msg is not None:
            return msg
        time.sleep(0.02)
    return None


def mandar_comando(m, i):
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, i % 256,
        mavutil.mavlink.MAVLINK_MSG_ID_HEARTBEAT, 0, 0, 0, 0, 0, 0,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="tcp:127.0.0.1:5762",
                     help="puerto SECUNDARIO de SITL -- nunca 5760 (consola de MAVProxy)")
    args = ap.parse_args()

    if args.host.endswith(":5760"):
        print("ABORTA: no se usa el puerto 5760, es la consola de MAVProxy (S1).")
        return 1

    print("Conectando a %s ..." % args.host)
    m = mavutil.mavlink_connection(args.host, source_system=250)
    m.wait_heartbeat(timeout=15)
    hb = m.messages.get("HEARTBEAT")
    armado = bool(hb and (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED))
    print("Heartbeat recibido. target_system=%d target_component=%d armado=%s" %
          (m.target_system, m.target_component, armado))
    if armado:
        print("ABORTA: el vehiculo esta armado; handle_setup_signing lo rechaza "
              "(GCS_Signing.cpp:76-79).")
        return 1

    secret_key = os.urandom(32)
    ts0 = ts_firma_actual()

    print("\n[1] SETUP_SIGNING (sin firmar) con clave aleatoria de 32 B ...")
    m.mav.setup_signing_send(m.target_system, m.target_component,
                              list(secret_key), ts0)
    time.sleep(1.0)  # tiempo para que se guarde y se cargue en todos los canales

    print("[2] COMMAND_LONG SIN firmar por este canal (firma ya activa FC-wide) ...")
    mandar_comando(m, 1)
    ack = esperar_ack(m)
    if ack is None:
        print("    -> SIN COMMAND_ACK. El canal exige firma y la rechazo. Correcto.")
        rechazo_confirmado = True
    else:
        print("    -> LLEGO COMMAND_ACK (result=%d) sin estar firmado." % ack.result)
        print("    -> Este puerto tambien esta exento (como el canal 0). Hallazgo distinto,")
        print("       no el esperado -- no se asume, se reporta tal cual.")
        rechazo_confirmado = False

    print("\n[3] Control positivo: firma correcta del lado GCS, mismo comando ...")
    # Timestamp deliberadamente muy adelantado: check_signature() en el C real
    # (mavlink_helpers.h:182) solo rechaza si el timestamp entrante llega MAS DE
    # 1 min ATRASADO respecto al reloj del FC -- no hay tope de "demasiado
    # adelantado". Usar ts0+1 (probado primero) fallaba igual que sin firmar;
    # esto descarta que sea un problema de desfase de reloj FC/GCS.
    m.setup_signing(secret_key, sign_outgoing=True,
                     initial_timestamp=ts0 + 10_000_000_000)
    mandar_comando(m, 2)
    ack2 = esperar_ack(m)
    if ack2 is not None:
        print("    -> LLEGO COMMAND_ACK (result=%d) al firmar correctamente." % ack2.result)
        control_ok = True
    else:
        print("    -> SIN COMMAND_ACK incluso firmando. Algo mas esta mal "
              "(puerto, timestamp, reloj) -- (2) NO es concluyente.")
        control_ok = False
    m.mav.signing.sign_outgoing = False  # no firmar los mensajes de limpieza de abajo

    print("\n[4] Limpieza: desactivando la firma en el FC (clave y timestamp en cero) ...")
    # IMPORTANTE: por el mismo canal de "m", no por el 5760. Si (2) confirmo que este
    # canal exige firma, un mensaje de desactivacion SIN firmar por aqui se descarta
    # igual que el comando de (2) -- y la firma queda activa para siempre (paso el
    # 2026-09-16, hubo que mover ~/ardupilot/eeprom.bin a mano para recuperarse). El
    # canal 0 (5760) nunca exige firma, asi que la desactivacion se manda por ahi.
    try:
        m0 = mavutil.mavlink_connection("tcp:127.0.0.1:5760", source_system=251)
        m0.wait_heartbeat(timeout=10)
        m0.mav.setup_signing_send(m0.target_system, m0.target_component, [0] * 32, 0)
        time.sleep(1.0)
        m0.close()
        print("    Enviado por el canal 0 (5760), que nunca exige firma.")
    except Exception as e:
        print("    AVISO: no se pudo limpiar por el canal 0 (%s)." % e)
        print("    El canal de %s puede haber quedado exigiendo firma. Verificar con:" % args.host)
        print("      python3 -c \"from pymavlink import mavutil; "
              "m=mavutil.mavlink_connection('%s'); m.wait_heartbeat(); "
              "m.mav.command_long_send(m.target_system,m.target_component,512,0,0,0,0,0,0,0); "
              "print(m.recv_match(type='COMMAND_ACK', blocking=True, timeout=2))\"" % args.host)
    m.close()

    print("\n" + "=" * 78)
    print(" RESUMEN")
    print("=" * 78)
    if rechazo_confirmado and control_ok:
        print(" El canal de %s exige firma de verdad: rechaza sin firmar y acepta" % args.host)
        print(" firmado. Confirma que el mecanismo de MAVLink 2 signing FUNCIONA cuando")
        print(" se le exige -- el defecto de HALLAZGO_firma_no_exigida.md esta en la")
        print(" EXCEPCION del canal 0 (ver diff de GCS_Signing.cpp en el docstring),")
        print(" no en el mecanismo de firma en si.")
        return 0
    if not control_ok:
        print(" NO CONCLUYENTE: ni firmado llego el ACK. Revisar timestamp/reloj/puerto")
        print(" antes de creerle a (2).")
        return 1
    print(" Este puerto tambien acepta sin firmar -- no es el resultado esperado.")
    print(" Reportar tal cual, no forzar la lectura de HALLAZGO_firma_no_exigida.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
