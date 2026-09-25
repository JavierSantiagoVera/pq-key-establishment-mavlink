# Hallazgo — el FC no exige firma a lo que le llega del GCS

**Fecha:** 2026-09-10. **Afecta a:** C2 (análisis de seguridad) y B4 (nonce).

```bash
py -3 experiments/signing_policy/firma_por_sentido.py
```

## Resumen

En la configuración evaluada, **el FC acepta y procesa comandos sin firma que llegan por el enlace
WiFi, incluso con la sesión KEMTLS ya activa**. La firma MAVLink 2 solo protege en la práctica el
sentido FC→GCS. El manuscrito afirma lo contrario: *«command injection [is] prevented»*
(`cas-sc-template.tex:1746`).

El núcleo del hallazgo es **la política del receptor**, que está en el código, y **no** el
comportamiento del GCS: aunque el GCS legítimo firmara, un atacante puede mandar tramas sin firma y
el FC las acepta igual.

---

## 1. Medido — cobertura de firma por sentido

Sin el dialecto HQC (que va en claro por diseño), contando desde la primera trama firmada de cada
captura:

| Sentido | Firmadas | Sin firma |
|---|---|---|
| FC → GCS, unicast `192.168.42.1 → .2` (sysid 1) | 8 928 | 3 148 |
| FC → broadcast `192.168.42.1 → .255` (sysid 1) | 0 | 1 333 |
| **GCS → FC** `192.168.42.2 → .1` (sysid 255) | **0** | **12** |

**Límite de la muestra:** solo las dos capturas `clear_fc_20251114_*` recogen los dos sentidos en
el WiFi, así que en el sentido GCS→FC hay **12 tramas**. Las otras capturas `fc_*` solo ven
FC→GCS.

## 2. Medido — comandos sin firma con la sesión activa

En las dos capturas bidireccionales, con la sesión ya activa, el GCS envía `COMMAND_LONG` con
`cmd = 512` (`MAV_CMD_REQUEST_MESSAGE`):

| | Antes de activarse | Con la sesión activa |
|---|---|---|
| `COMMAND_LONG` del GCS | sin firma, en claro | **sin firma, en claro** |
| `COMMAND_ACK` del FC | sin firma, legible (`cmd=512`, `result=0`), +16 ms | **firmado, no legible**, +15 a +37 ms |

Son 6 comandos con la sesión activa en cada captura, y **todos reciben su `COMMAND_ACK`**.

## 3. Por qué el FC los acepta — código

| Archivo | Qué hace |
|---|---|
| `GCS_Signing.cpp:116-122` | `accept_unsigned_callback` devuelve `true` **siempre** en el canal 0: *«always accept channel 0, assumed to be secure channel. This is USB on ChibiOS boards»* |
| `GCS_Signing.cpp:244` ss. | `enable_signing_with_key` asigna `link_id = número de canal` |
| capturas | **las 9 239 tramas firmadas llevan `link_id = 0`** → el enlace WiFi es el **canal 0** |
| `GCS_Common.cpp:1965` | solo se despachan las tramas con `MAVLINK_FRAMING_OK`; una trama que falla el chequeo de firma no llega a `packetReceived()` y no genera `COMMAND_ACK` |

Encadenado: el WiFi es el canal 0 → el canal 0 acepta tramas sin firma → los comandos sin firma se
despachan → el FC contesta con un ACK. **El ACK es la prueba de que el comando pasó el filtro.**

> `NO VERIFICADO` — la función `mavlink_frame_char_buffer`, que es la que devuelve
> `BAD_SIGNATURE` cuando el callback responde `false`, está en la librería C de MAVLink, que se
> genera al compilar y **no está en este snapshot** (no hay `modules/` ni `.gitmodules`). Aquí se da
> por buena la especificación de MAVLink 2.

> **Inferido, no leído:** el ACK posterior a la activación va cifrado, así que su `result` no se
> puede leer. Que corresponda a ese comando se deduce del emparejamiento y de la temporización
> (15–37 ms, como los 16 ms de antes de activarse).

## 4. La criptografía: por qué esto es un defecto

**Una firma que el receptor no exige no protege nada.** La firma MAVLink 2 es un MAC — un código
calculado con una clave compartida que prueba que quien envía la trama conoce esa clave. Pero solo
sirve si el receptor **rechaza** lo que no la tiene o no la verifica. Si el receptor acepta tramas
sin firma, el atacante ni siquiera intenta falsificarla: manda la trama sin firma y ya. Por eso la
**política de aceptación** forma parte de la seguridad, no es un detalle de implementación.

**Autenticar el handshake no es autenticar el canal.** El handshake KEMTLS-PDK sí autentica al GCS:
solo quien tiene `sk_s` puede completarlo. Eso es *autenticación de entidad* — prueba quién está al
otro lado **en ese momento**. Lo que haría falta después es *autenticación del origen de cada
mensaje*: que cada comando posterior demuestre que viene de esa misma entidad, firmado con la
`k_sign` que salió del handshake. Ese segundo eslabón existe en el código (se deriva `k_sign`, se
activa la firma), pero el receptor no lo exige. El manuscrito salta del primero al segundo
(`l. 1746`: la inyección se evita *porque* solo el GCS legítimo puede completar el handshake), y
en ese salto está el fallo.

**Un supuesto de seguridad que no sobrevive al cambio de plataforma.** El comentario lo dice: el
canal 0 se da por seguro porque en las placas ChibiOS es un **cable USB** — hace falta acceso físico.
En el Bebop, con Linux, el canal 0 es `SERIAL0`, es decir, **el enlace UDP por WiFi**. El supuesto
se trasladó sin revisarlo de un cable a un enlace de radio. Es un error de portabilidad clásico.

## 5. Qué afirma el manuscrito y dónde choca

| Línea | Afirmación | Choque |
|---|---|---|
| 135 | *«MAVLink 2 signing continues to provide message authenticity and freshness»* | no en el sentido GCS→FC |
| 1224 | modelo de adversario: *«inject new MAVLink frames»* | con su propio modelo, una inyección sin firma **funciona** |
| 1378-1381 | *«authenticity and freshness according to the receiver's signing policy»* | técnicamente cierto — la política es aceptar sin firma en el canal 0 —, pero ningún lector lo va a deducir |
| `tab:security_goals`, fila *Data-plane integrity* | *«signing is applied to protected frames, so ciphertext modification is detected before acceptance»* | a GCS→FC no se le aplica |
| 1746-1749 | *«Active spoofing and command injection are prevented by unilateral authentication of the GCS»* | **es la afirmación que no se sostiene** |

## 6. Alcance y límites

- **Observado solo con `MAV_CMD_REQUEST_MESSAGE`**, que es inocuo. No se ha probado con comandos de
  control (armar, cambiar de modo, despegar). Pero en el canal 0 la aceptación **no depende del
  `msgid`**, así que el resultado se generaliza por el código, no por la observación.
- **n = 12** tramas GCS→FC, en 2 capturas.
- Las dos capturas se llaman `clear_fc_*`. Si «clear» significa que el GCS tenía el cifrado
  apagado, eso explicaría que los comandos del GCS vayan en claro, pero **no afecta al hallazgo**:
  la política del FC es la misma con cifrado o sin él. `NO VERIFICADO` qué significa «clear».
- No se sabe si el GCS habría firmado en las corridas con cifrado: no hay capturas bidireccionales
  de esas corridas en el WiFi.

## 7. Dos observaciones más, sin explicar todavía

- **Firma intermitente del FC en las corridas de estrés.** En R1, con la sesión activa, FC→GCS
  alterna rachas firmadas y sin firmar: 35 rachas en total, una pareja por sesión (R1 tiene 18
  handshakes). Las tramas sin firma son sobre todo `STATUSTEXT` (251). No se ha encontrado el
  mecanismo: `HqcSession::reset()` (`GCS_KEMTLS.cpp:513-529`) no toca la firma.
- **El broadcast `.255` nunca va firmado** (1 333 tramas). **Investigado el 2026-09-17,
  sin cerrar:** `send_heartbeat()` y el resto de mensajes usan el mismo
  `mavlink_msg_..._send()` de siempre (`GCS_Common.cpp:3150-3152`) — no hay una rama de
  código que trate el broadcast distinto a nivel de mensaje. El driver UDP de SITL para
  `:bcast` (`~/ardupilot/libraries/AP_HAL_SITL/UARTDriver.cpp:674-686`, código de
  ArduPilot, no del fork) tampoco hace nada especial: es un socket UDP normal,
  `connect()` a la IP de broadcast con `SO_BROADCAST`, igual que cualquier otro puerto
  serie. **Se descarta que sea un caso especial a nivel de mensaje o de socket.** Queda
  como hipótesis más probable, sin verificar contra código que no está en ningún
  snapshot disponible: que el canal de broadcast del Bebop no tenga cargada su clave de
  firma por algo específico de la configuración de esa corrida (`load_signing_key()`
  corre por canal, y un canal sin clave cargada nunca firma su saliente) — pero eso no
  se puede comprobar sin la configuración exacta de arranque que se usó en 2025-11-13.

## 8. Corrección sobre dónde se cifra

Antes se dijo que el cifrado del plano de datos lo hacía «el componente ausente», `hqc-mavlink-proxy`.
**Queda matizado.** El ACK del FC es legible antes de activarse la sesión e ilegible después, lo que
indica que **el FC sí cifraba** en esas corridas. En el lado del FC, quien llama a
`mavlink_get_crypt_config` es con toda probabilidad la librería C de MAVLink modificada — el
manuscrito sitúa el cifrado en `mavlink_finalize_message_buffer()` (l. 986) —, que se genera al
compilar y **no está en el snapshot**. El proxy sería la contraparte del lado GCS (*«to match your
proxy/tap»*). **Son dos componentes ausentes, no uno.**

## 9. Qué decidir

> **Actualización 2026-09-16:** arreglar y medir sigue en pie, y es fiel al artículo (l. 1112 y 1378 ya
> dicen que el FC verifica la firma). El **par de proxies queda en suspenso** por cambiar la arquitectura;
> la vía fiel es corregir `accept_unsigned_callback` en el fork. Ver `08_cierre/MENSAJE_NICOLAS_PLAN.md`.
>
> ~~**Decidido (Javier, 2026-09-15): arreglar y medir, con un par de proxies.**~~ El firmware no se
> puede recompilar desde el snapshot, así que la tabla de abajo queda resuelta por la segunda fila.
> ArduPilot stock escucha solo en localhost y proxy-FC descarta todo lo que no venga firmado. Diseño:
> [`../proxy_c9/DISENO.md`](../proxy_c9/DISENO.md); prueba de inyección: `08_cierre/PLAN_CAMPANA.md` §4.2.

## 10. Confirmación en vivo contra SITL stock, sin el fork (2026-09-16)

Experimento #3 de `08_cierre/README.md` §B-bis: [`firma_en_sitl.py`](firma_en_sitl.py),
contra el SITL de S1 (ArduPilot puro, ninguna línea del fork KEMTLS).

**Estático, sin correr nada:** `diff` entre `GCS_Signing.cpp` del fork
(`02_repo/.../libraries/GCS_MAVLink/GCS_Signing.cpp`) y el mismo archivo en el árbol de
SITL (`~/ardupilot/libraries/GCS_MAVLink/GCS_Signing.cpp`) — **`accept_unsigned_callback()`
no cambia una línea.** El fork solo añade `enable_signing_with_key()` (una API en runtime
para activar la firma con la `k_sign` del handshake); no toca la política de aceptación.
**La excepción del canal 0 no es un defecto de este proyecto, es herencia de ArduPilot.**

**En vivo, medido, repetible:** con la firma activada en el FC (`SETUP_SIGNING`), un
`COMMAND_LONG` sin firmar por un canal que no es el 0 (puerto 5762 de SITL) **no recibe
`COMMAND_ACK`** — el mecanismo de rechazo funciona de verdad, no solo en el papel.

**Confirmado el 2026-09-17 — control positivo completo.** El 2026-09-16 el control
positivo (firmar correctamente con la misma clave y que el comando SÍ se acepte) no se
lograba: `COMMAND_ACK` nunca llegaba, ni firmando. Repetido hoy contra un SITL con
`eeprom.bin` limpio (ver más abajo, el efecto secundario de esa corrida vieja), el mismo
script funciona de punta a punta: rechaza sin firmar, **acepta firmado
(`COMMAND_ACK result=0`)**. La causa más probable del fallo de ayer: una clave de firma
vieja, persistida en `~/ardupilot/eeprom.bin` de una corrida anterior, interfería con la
nueva — no se puede confirmar con certeza retroactivamente, pero con el eeprom limpio el
resultado es reproducible. Conclusión ya no parcial: **el mecanismo de firma MAVLink 2
funciona correctamente cuando se le exige** — el defecto está exclusivamente en la
excepción del canal 0, no en la firma en sí.

**Efecto secundario en el SITL que quedó corriendo — importante para la próxima sesión:**
el experimento activó la firma en el canal de escucha secundario (puerto 5762) con una
clave aleatoria que solo vivió en la memoria del script, y el intento de desactivarla al
final (`SETUP_SIGNING` con clave en cero) **se descartó por el mismo motivo que se estaba
probando** — ese canal ya exige firma, así que un mensaje de desactivación sin firmar no
llega. Confirmado: tras la corrida, un comando sin firmar por 5762 sigue sin `COMMAND_ACK`.
La consola de MAVProxy en el puerto 5760 (canal 0) **no se vio afectada** — sigue
respondiendo normal, porque el canal 0 nunca exigió firma para empezar.
**Resuelto el 2026-09-17.** Reiniciar `arducopter` solo no bastaba: la clave de firma vive
en `~/ardupilot/eeprom.bin` (almacenamiento persistente de ArduPilot) y se recargaba igual
en cada arranque. Hubo que mover ese archivo aparte (no borrarlo:
`eeprom.bin.bak_20260917_firma_stuck` y `eeprom.bin.stale_firma_20260917`, ambos en
`~/ardupilot/`, fuera del repo) para que ArduPilot arrancara con uno nuevo por defecto.
Costo: se perdieron los parámetros/calibración que hubiera en ese eeprom -- para SITL con
la configuración por defecto de Copter, sin ajustes manuales previos conocidos. Verificado:
`COMMAND_LONG` sin firmar por el puerto 5762 vuelve a recibir `COMMAND_ACK` (result=0). La
consola de MAVProxy que estaba abierta se cerró en el proceso (dependía del mismo
`arducopter`, que hubo que matar y relanzar). El `arducopter` nuevo quedó corriendo solo,
sin consola, escuchando en 5760/5762/5763. Para reabrir una consola apuntando a **ese mismo
proceso** (sin lanzar un segundo `arducopter` que chocaría por el puerto 5760):
`mavproxy.py --master tcp:127.0.0.1:5760 --console`. Si en cambio se corre
`sim_vehicle.py -v ArduCopter --console` de nuevo, primero hay que matar este `arducopter`
(`pkill -f build/sitl/bin/arducopter`) para liberar el puerto.

**`firma_en_sitl.py` ya no deja este efecto secundario.** El paso de limpieza ahora manda
la desactivación por una conexión aparte al puerto 5760 (canal 0, que nunca exige firma),
en vez de por el mismo canal que acaba de activar la firma. Probado el 2026-09-17: se
puede correr el script las veces que haga falta sin dejar el SITL atascado.

**Para el artículo, una de dos:**

1. **Arreglarlo y medirlo:** que el GCS firme (lo implementamos en C9) **y** que el FC rechace en el
   enlace las tramas sin firma.
2. **Retirar la afirmación:** declarar la inyección de comandos como limitación, igual que ya se
   hace con el nonce.

**Si se arregla, hay que hacer cumplir la firma en el FC, y hay dos formas:**

| Opción | Pro | Contra |
|---|---|---|
| **Cambiar el firmware:** que `accept_unsigned_callback` no acepte el canal 0 cuando hay una sesión KEMTLS activa | unas pocas líneas | rompe el principio de la fase C: «cripto en el enlace, nunca dentro del firmware» |
| **Proxy en el propio Bebop**, en su Linux, delante de ArduPilot, que descarte las tramas sin firma | respeta el principio | más trabajo, y añade un salto cuya latencia hay que medir en C10 |

**Efecto sobre B4:** la opción 1 depende de que las tramas lleguen firmadas, y hoy las del GCS no lo
están. Pero el cumplimiento de la firma en los dos sentidos **hace falta de todos modos** para que se
sostenga la afirmación de integridad. Una vez exigida, la opción 1 no añade ningún byte a lo que ya
cuesta la firma (13 B por trama GCS→FC, que es el precio de la autenticidad que el artículo afirma).
La opción 3 costaría esos mismos 13 B **más** 8 B.

## 11. Opción 1 implementada y medida en SITL (2026-09-17)

Con permiso de Javier, se implementó y probó la opción 1 de la tabla de arriba —no como
sugerencia, como código corrido de verdad. Parche de una función, en
[`parche_canal0.patch`](parche_canal0.patch) (contra `~/ardupilot`, no contra este
repositorio, porque `GCS_Signing.cpp` es código de ArduPilot, no del fork ausente):

```diff
-    if (status == mavlink_get_channel_status(MAVLINK_COMM_0)) {
-        // always accept channel 0, assumed to be secure channel. This
-        // is USB on ChibiOS boards
-        return true;
-    }
+    // se quita la excepcion de "canal 0 = USB, siempre seguro": en el Bebop
+    // el canal 0 es el enlace WiFi.
```

**Medido, contra SITL recompilado con el parche, por el puerto 5760 (canal 0 — el único
que antes tenía el pase libre; los demás canales ya se habían probado en §10):**

| Prueba | Antes del parche | Con el parche |
|---|---|---|
| `COMMAND_LONG` sin firmar por canal 0 | **Se acepta** (`COMMAND_ACK`) — el defecto | **Se rechaza** (sin `COMMAND_ACK`) |
| El mismo comando, firmado correctamente | Se acepta | Se acepta (control positivo: el rechazo de arriba es por falta de firma, no por otra cosa) |

**El parche se revirtió después de medir** (`git checkout` sobre un working tree limpio,
recompilado): esta sesión no deja `~/ardupilot` modificado de forma permanente, porque es
una herramienta externa al repositorio, no el propio proyecto. El parche queda guardado
como artefacto reproducible en `parche_canal0.patch` — aplicar con
`git apply parche_canal0.patch` desde `~/ardupilot` para repetir la medición.

**Lo que esto SÍ cierra:** dentro del alcance del contra-ejemplo (`accept_unsigned_callback`
es código genérico de ArduPilot, no del fork), la fila "Data-plane integrity" de
`tab:security_goals` y la afirmación de la l. 1746 (*"command injection is prevented"*)
dejan de ser una limitación sin solución conocida — hay un parche de una función,
implementado y medido, que las hace ciertas. **Lo que NO cierra:** aplicar esto en el
Bebop real requiere el firmware del fork (esta prueba fue en SITL, con
`GCS_Signing.cpp` stock, no con el fork de Nicolás, que puede o no compartir ese mismo
archivo sin cambios — no verificado, aunque el diff de §10 sugiere que sí).

## 12. La GCS también firma — arnés completo, medido de punta a punta (2026-09-17)

La mitad que faltaba del hallazgo original (§1: *"GCS→FC firmadas: 0 de 12"*) — la GCS
nunca firma — se cerró en `arnes_baseline.py`, no como script de prueba suelto sino como
parte del arnés de medida que ya se usa para M1–M3: flag `--firmar` (función
`activar_firma_gcs()`). Manda `SETUP_SIGNING` y firma los `COMMAND_LONG`/`TIMESYNC`/
`SET_MESSAGE_INTERVAL` salientes; no verifica la firma de lo que manda el FC de vuelta
(no es el objetivo de este arnés — eso ya lo audita `firma_en_sitl.py`).

**Medido con el parche de §11 aplicado, contra el canal 0 (5760) — FC exigiendo firma de
verdad, GCS firmando de verdad, 20 s por métrica:**

| Métrica | n | perdidos |
|---|---|---|
| M1 comando→ACK | 200 | **0** |
| M2 TIMESYNC | 200 | **0** |
| M3 ATTITUDE (huecos > 100 ms) | 999 muestras | **0** |

Percentiles en el rango habitual de las corridas sin firma (p50 ≈ 3 ms en M1/M2, p99 ≈
20–23 ms — el firmado añade una cola en p99 de M1 frente a p50, coherente con el costo
extra de calcular/verificar HMAC, pero no pérdidas). **Conclusión:** con las dos mitades
arregladas (FC exige, GCS firma), el sistema funciona igual de bien que sin firma — la
integridad de datos que afirma `tab:security_goals` deja de depender de una excepción
que la anula, y no cuesta disponibilidad medible en este ensayo.

Parche revertido después de medir, igual que en §11. `arnes_baseline.py --firmar` queda
en el repo como capacidad permanente del arnés (no un script desechable), lista para usar
el día que haya un FC que también lo exija de verdad (parche aplicado, o el fork).

## 13. Pruebas de inyección I1/I3/I4 en SITL (2026-09-17)

`08_cierre/PLAN_CAMPANA.md` §4.2 diseñó I1–I6 para el Bebop real con el proxy. Sin
ninguno de los dos, `inyeccion_sitl.py` prueba I1 (ya cubierto en §11-12), I3 y I4
directamente contra la firma MAVLink 2 — no hace falta el proxy para probar el
**mecanismo de rechazo en sí**. Corre en **SITL stock, canal no-0 (5762), sin el parche
de canal 0** — ese canal ya exige firma sin tocar nada.

| Prueba | Cómo se fabrica la trama | Resultado esperado | Medido |
|---|---|---|---|
| Control | Trama firmada correctamente | Se acepta | ✅ `COMMAND_ACK` |
| **I3** — replay | Los mismos bytes exactos de la trama de control, reenviados tal cual | 0 ACK (mismo timestamp, ya visto) | ✅ 0 ACK |
| **I4** — bit-flip | Payload distinto (otra `confirmation`), CRC recalculado para que sea autoconsistente, pero con la **firma de la trama de control** (de otro contenido y otro timestamp) pegada al final | 0 ACK (CRC pasa, la firma no coincide con este contenido) | ✅ 0 ACK |
| Control final | Una trama nueva, firmada bien, después de los dos ataques | Se acepta (el canal no quedó roto) | ✅ `COMMAND_ACK` |

**Qué NO se hizo, y por qué:**
- **I2** (mismo ataque a todos los puertos UDP) no aporta nada nuevo sobre I1 en esta
  topología de un solo puerto.
- **I5** (reflejar una trama del FC hacia el FC) necesita la topología de dos proxies
  que está en suspenso.
- **I6** (`HELLO` sin autenticar con la sesión activa) necesita el estado del handshake
  KEMTLS (`GCS_KEMTLS.cpp`), que no está en SITL — solo existe en el fork.

**Lo que esto cierra:** confirma con bytes reales, no solo con la especificación, que la
firma MAVLink 2 rechaza tanto el replay exacto como la manipulación de contenido con una
firma ajena — las dos propiedades que `tab:security_goals` le atribuye ("Replay
resistance", "Data-plane integrity"). **Lo que NO cierra:** sigue siendo el mecanismo de
firma en abstracto, no el sistema KEMTLS completo (que necesita el fork para I6 y el
Bebop real para I2/I5 con la topología de proxies).
