# C9 — Par de proxies con la construcción corregida (diseño)

**Fecha:** 2026-09-15 · **Estado:** diseño **en suspenso**, sin implementar · **Dueño:** sesión principal

> **En suspenso (2026-09-16).** Criterio de Javier: lo que cambia lo propuesto en el artículo se
> consulta antes con Nicolás. Este diseño cambia dos cosas del artículo: la arquitectura (l. 909, cripto
> en el firmware) y el nonce (l. 1470-1473 especifica contador explícito de ≥64 bits con ventana de
> replay, que es la opción 3 de B4, no la 1). Queda como **sugerencia** en
> [`08_cierre/MENSAJE_NICOLAS_PLAN.md`](../../08_cierre/MENSAJE_NICOLAS_PLAN.md) §3.

**Decisiones de Javier (2026-09-15):**

- **Arquitectura:** par de proxies.
- **Inyección de comandos:** se arregla y se mide.
- **B4:** opción 1, el timestamp de la firma como nonce.

Plan de medida: [`08_cierre/PLAN_CAMPANA.md`](../../08_cierre/PLAN_CAMPANA.md).

---

## 0. Por qué un par de proxies y no el firmware

| | Fuente |
|---|---|
| El snapshot **no compila**. `02_repo/` solo trae `libraries/AP_KEM`, parte de `libraries/GCS_MAVLink`, `Tools/` y las capturas. No están `waf`, `ArduCopter` ni la librería C de MAVLink, y `mav_crypt_alg_t` no se define en ningún archivo | medido, `ls` + `grep` del 2026-09-15 |
| No hay otra copia del fork en esta máquina | `find` en `Desktop`, `Documents` y `Downloads` |
| Hay binario oficial de ArduPilot para el Bebop | `firmware.ardupilot.org/Copter/stable/bebop/` (`arducopter`, `git-version.txt`), visto el 2026-09-15 y fechado el 2026-09-02 |

**Qué se conserva del artículo:** el protocolo KEMTLS-PDK (mensajes 61000–61008, transcript, FINISH y HKDF).

**Qué cambia:** *dónde* vive. La l. 909 del manuscrito dice que la cripto está integrada en el firmware, y hay que reescribirla. **No se toca el `.tex`**: la redacción es de Javier.

---

## 1. Topología

```
 app GCS (pymavlink/QGC)                                              arducopter STOCK
   udp 127.0.0.1:14550                                                -A udp:127.0.0.1:14551
          │                                                                     │
   ┌──────┴───────┐     WiFi 2,4 GHz, UDP                        ┌──────────────┴───┐
   │  proxy-GCS   │  192.168.42.2:14600  ⇄  192.168.42.1:14600   │    proxy-FC      │
   │  iniciador   │  ───── tramas firmadas y cifradas ─────      │   respondedor    │
   │  (sk_s)      │                                              │   (pk_s, PDK)    │
   └──────────────┘                                              └──────────────────┘
      portátil Linux                                                Linux del Bebop
```

Los puertos son parámetros; los de arriba son solo los valores por defecto.

**Por qué ArduPilot queda fuera del alcance del WiFi — inferido, se verifica en C11 (I2):**

1. Con `-A udp:127.0.0.1:14551`, ArduPilot es un **cliente** UDP. Un socket con `connect()` solo recibe datagramas de ese par, y el kernel descarta los demás.
2. Linux descarta los paquetes con origen `127.0.0.0/8` que llegan por una interfaz que no es `lo` (paquetes marcianos), así que tampoco se puede suplantar el origen desde el WiFi.

Consecuencia: **lo único que escucha en el WiFi es proxy-FC**, y proxy-FC no deja pasar nada que no venga firmado. Así se arregla la inyección, y así se prueba en C11: se inyecta en *todos* los puertos UDP abiertos del Bebop.

---

## 2. Handshake — se conserva, con cuatro cambios

Roles como en `GCS_KEMTLS.cpp`:

- **GCS = iniciador.** Tiene `sk_s` y genera el par efímero `pk_e`/`sk_e`.
- **FC = respondedor.** Lee `pk_s` del archivo PDK, encapsula `ct_s` hacia `pk_s` y `ct_e` hacia `pk_e`, y verifica el FINISH.

| Paso | Mensaje | Qué pasa |
|---|---|---|
| 1 | `HELLO` 61000 G→F | `session_id`, `salt`, `rc`, oferta. Abre el transcript |
| 2 | `HELLO_ACK` 61001 F→G + `CT_CHUNK` 61003 (`ct_s`) | el FC encapsula hacia `pk_s` del PDK |
| 3 | `PK_CHUNK` 61002 G→F / `PK_ACK` 61007 | fragmentos de `pk_e` (2249 B / 220 = 11), con SACK |
| 4 | `CT_CHUNK` 61003 F→G / `CT_ACK` 61004 | el FC encapsula hacia `pk_e` y manda `ct_e` y `ct_s` (4433 B / 220 = 21 cada uno) |
| 5 | `FINISH` G→F | `tag = HMAC(finished_key, th)`. Solo quien decapsula `ct_s` con `sk_s` puede calcularlo |
| 6 | `STATUS` 61006 F→G | OK → sesión activa |

**Por qué autentica al GCS y no al FC** (queda como estaba, declarado): `ct_s` encapsula hacia la clave pública estática del GCS. Solo el poseedor de `sk_s` recupera `ss_s`, y sin `ss_s` no se deriva `finished_key`. El FC no tiene clave estática propia, así que nadie le puede exigir que pruebe quién es. Esto es autenticación **unilateral**.

**Los cuatro cambios:**

| # | Cambio | Por qué |
|---|---|---|
| H1 | `version = 2` en `HELLO`, prefijo HKDF `ardupilot-hqc-v2:` | que el sistema viejo y el nuevo **no puedan mezclarse**: separación de dominio entre versiones |
| H2 | un `HELLO` nuevo **no destruye la sesión activa** hasta que su `FINISH` verifica | el firmware hacía `hqc_.reset()` al recibir cualquier `HELLO` (`GCS_KEMTLS.cpp:563`). Un solo paquete sin autenticar tumbaba la sesión |
| H3 | solo ChaCha20; se retira AES-CTR — **propuesta, a confirmar por Javier** | una sola construcción que probar. El Cortex-A9 del Bebop no tiene instrucciones AES, y ChaCha20 está pensado para software |
| H4 | layout de mensajes redefinido | el XML del dialecto no está en el snapshot. Los tiempos por fase se miden por `msgid`, que no depende del layout |

Los mensajes HQC van **sin firma y en claro por diseño**: todavía no hay clave. proxy-FC acepta sin firma *solo* los `msgid` 61000–61008, y esos mensajes nunca llegan a ArduPilot.

---

## 3. Derivación de claves

Igual que hoy hasta el PRK:

```
salt32 = SHA-256(salt ‖ LE64(session_id))
PRK    = HKDF-Extract(salt32, ss_e ‖ ss_s)
X      = HMAC-SHA256(PRK, "ardupilot-hqc-v2:" ‖ label ‖ 0x01)[0:L]
```

| Label | L | Uso |
|---|---|---|
| `finished` | 32 | clave del tag de FINISH |
| `enc:g2f` / `enc:f2g` | 32 | clave ChaCha20 por sentido |
| `iv:g2f` / `iv:f2g` | 12 | base del nonce por sentido |
| `sign:g2f` / `sign:f2g` | 32 | clave de firma **por sentido** (hoy: una sola `sign`) |

**Por qué `g2f`/`f2g` y no `tx`/`rx`.** «tx» significa cosas opuestas en cada extremo: el tx del FC es el rx del GCS. Si un extremo deriva mal y usa `key:tx` para lo que *él* transmite, los dos sentidos cifran con la misma clave y el mismo IV. Eso es reutilizar el keystream entre sentidos, el mismo defecto que estamos corrigiendo, pero entrando por otra puerta. Nombrar el sentido absoluto (GCS→FC) hace que ese error no se pueda escribir.

**Por qué una clave de firma por sentido.** Con una sola `k_sign`, una trama firmada que el FC envía al GCS se puede **reflejar**: el atacante la captura y se la devuelve al FC. La firma es válida, porque es la misma clave, y el FC la aceptaría como si viniera del GCS. Con `sign:f2g` ≠ `sign:g2f`, la trama reflejada no verifica. Es separación de dominio: cada clave sirve para un solo propósito y un solo sentido.

---

## 4. Plano de datos — opción 1

### 4.1 Emisión (una trama MAVLink 2 de la app local)

1. `ts_d ← ts_d + 1`: contador de 48 bits por sentido, que empieza en 1 en cada sesión. **Si llega a 2⁴⁸−1, la sesión se corta** (fail-closed), no se envuelve.
2. `nonce = iv_d ⊕ (0x00·6 ‖ BE48(ts_d))`, y `payload ← payload ⊕ ChaCha20(enc_d, nonce, contador de bloque = 0)`.
3. El CRC se recalcula **sin tabla de `CRC_EXTRA`**, aprovechando que el CRC es afín (§4.4).
4. `incompat_flags |= 0x01`, `link_id` = 1 (g2f) o 2 (f2g), `timestamp = ts_d`.
5. `firma = SHA-256(sign_d ‖ cabecera[10] ‖ payload_cifrado ‖ CRC ‖ link_id ‖ ts)[0:6]`. Es la firma MAVLink 2 estándar, solo que con clave por sentido.

### 4.2 Recepción — en este orden, sin excepciones

| # | Comprobación | Si falla |
|---|---|---|
| 1 | ¿Trama firmada? Sin firma, solo pasa si su `msgid` ∈ 61000–61008, y va al handshake | `DROP unsigned` |
| 2 | ¿Hay sesión activa? | `DROP nokey` |
| 3 | Firma con `sign_d`, comparación en tiempo constante | `DROP badsig` |
| 4 | `ts > last_ts_d`; se actualiza **solo después** de verificar | `DROP replay` |
| 5 | Descifrar, restaurar el CRC, **quitar la firma** (flag y 13 B) y entregar a la app local | — |

Cada `DROP` incrementa un contador por motivo y se registra en el log. C11 comprueba que cada ataque cae en el motivo esperado.

**Por qué verificar antes de descifrar.** Descifrar un cifrado falsificado da un claro que el atacante controla a medias: si voltea un bit del cifrado, voltea el mismo bit del claro, porque el cifrado de flujo es XOR. Entregar eso, o reaccionar a ello de cualquier forma, abre la puerta a oráculos. Lo que no está autenticado no se toca.

**Por qué actualizar `last_ts` después de verificar.** Si se actualizara antes, una trama falsificada con `ts = 2⁴⁸−2` subiría el umbral, y todas las tramas legítimas posteriores se descartarían como repeticiones. Sería una denegación de servicio con un solo paquete.

### 4.3 Por qué el nonce va así — el defecto que corrige

ChaCha20 (RFC 8439) genera el keystream por bloques de 64 B: `bloque_i = F(clave, nonce, contador = i)`. Una payload MAVLink de hasta 255 B consume los bloques 0 a 3.

**El diseño viejo** metía el número de secuencia en el **contador** (`GCS_KEMTLS.cpp:269-270`, `*counter0 = seq`), con clave y nonce fijos. La trama *n* usa los bloques *n…n+3* y la *n+1* usa *n+1…n+4*: **comparten tres bloques**. Por eso colisiona ya en la segunda trama, y XOR de los dos cifrados da XOR de los dos claros, sin la clave.

**El diseño nuevo** mete el valor por mensaje en el **nonce** y deja el contador en 0. Cada trama tiene un nonce propio, y los keystreams no se solapan nunca mientras el par (clave, nonce) no se repita:

- **Dentro de una sesión**, `ts_d` es estrictamente creciente, así que no se repite. Además, B4 midió que el campo es un contador y no un reloj.
- **Entre sesiones**, `enc_d` cambia en cada handshake, porque el PRK depende de `ss_e`, que viene de un par efímero nuevo.

**Qué es y qué no es la construcción.** Es *encrypt-then-MAC* con un tag de 48 bits, la firma MAVLink 2. **No es un AEAD estándar**, y el artículo no debe llamarlo AEAD. Se declara:

- **Falsificación:** probabilidad 2⁻⁴⁸ por intento. El atacante tiene que *enviar* cada intento por el enlace, así que la fuerza bruta en línea está limitada por el ancho de banda.
- **La firma es `SHA-256(clave ‖ datos)`, no HMAC.** Esa forma es vulnerable a extensión de longitud *cuando se publica el hash completo*. Aquí se publican 6 B de 32, y sin el estado interno completo del hash la extensión no es posible.
- **Metadatos en claro:** `msgid`, `sysid`, longitud y `seq` quedan visibles.

### 4.4 El CRC sin `CRC_EXTRA`

El CRC de MAVLink (X.25) es **afín**: para entradas de igual longitud se cumple `crc(x⊕y⊕z) = crc(x)⊕crc(y)⊕crc(z)`. Con `x = cab‖P‖e`, `y = 0‖P‖0` y `z = 0‖C‖0` sale `x⊕y⊕z = cab‖C‖e`. Así se obtiene el CRC del cifrado a partir del CRC del claro sin conocer el byte `CRC_EXTRA` (`e`) del mensaje, y el proxy no depende de la tabla del dialecto.

Es aritmética. **Se valida contra tramas reales** antes de creerle (test T2).

### 4.5 Qué hay que declarar (condiciones de B4)

| Condición | En este diseño |
|---|---|
| La confidencialidad depende de que la firma esté activa | **estructural:** no existe camino sin firma salvo los `msgid` HQC, que nunca llegan a ArduPilot |
| La unicidad entre sesiones la dan claves frescas | por derivación, §3 |
| Reordenamiento | `ts` estrictamente creciente, así que **una trama que llega reordenada se descarta**. C11 mide cuántas. Si fueran demasiadas, se cambia a ventana deslizante: decisión con datos, no ahora |
| Coste | 13 B por trama en los dos sentidos, que es la firma. **La opción 1 no añade nada más**; B6 lo mide |

---

## 5. Implementación

| | |
|---|---|
| Programa | `hqcproxy --role gcs\|fc --mode passthrough\|crypto`, C99, POSIX, un único bucle `select()` (base: `Tools/UDP_Proxy/udpproxy.c`) |
| KEM | PQClean HQC-128 `clean`, de `libraries/AP_KEM/vendor/`, con el shim de RNG parcheado en A3 |
| Primitivas | SHA-256, HMAC, HKDF y ChaCha20 propios, validados con vectores de RFC (T1). Sin dependencias externas: el Bebop no tiene librerías |
| PDK | mismo formato de 56 B de cabecera (`ap_kem_file.h`, magic `0x544D454B`), generado con `make_pdk_from_so.py` o con una herramienta equivalente |
| Log | CSV por trama: `sentido, msgid, len, t_in_ns, t_out_ns, veredicto`, con `CLOCK_MONOTONIC`. Es la instrucción de medida **declarada** que le faltaba al artículo |
| `passthrough` | mismo camino de código y los mismos timestamps, sin cripto. Es la condición B del plan: permite restar el coste del proxy aparte del de la cripto |
| Compilación cruzada | `arm-linux-gnueabihf-gcc -static` en el portátil. `NO VERIFICADO` que un binario estático arranque en el kernel del Bebop 1: se prueba el día 0 con un hola-mundo |

Directorio previsto: `experiments/proxy_c9/{src,test,tools}`.

---

## 6. Tests (B5), todos antes de tocar el dron

| # | Test | Qué valida |
|---|---|---|
| T1 | vectores: SHA-256 (FIPS 180-2, «abc»), HMAC (RFC 4231 casos 1–2), HKDF (RFC 5869 caso 1), ChaCha20 (RFC 8439 §2.4.2) | que las primitivas son las que dicen ser |
| T2 | CRC X.25 contra `HEARTBEAT` reales de las capturas (`CRC_EXTRA` = 50) + identidad afín de §4.4 | el códec MAVLink, con datos reales |
| T3 | firma contra la implementación de referencia de pymavlink (portátil Linux) | el layout de 13 B, que en B4 quedó `NO VERIFICADO` |
| T4 | 300 y 70 000 tramas: ningún par (clave, nonce) repetido y ningún bloque de keystream compartido. **Control positivo:** el mismo test sobre la construcción vieja **debe fallar** en la trama 2 | la corrección del nonce, y que el test detecta el defecto |
| T5 | sin firma, firma mala, repetición, reflexión f2g→FC, bit volteado en el cifrado, cabecera alterada, sin sesión → cada uno cae en su `DROP` | fail-closed, por motivo |
| T6 | handshake completo en memoria con los dos roles; FINISH con tag malo → rechazo; `HELLO` sin autenticar con sesión activa → la sesión sigue | protocolo y H2 |
| T7 | ensayo integral en el portátil: ArduCopter SITL + los dos proxies + arnés de medida + inyección | todo el montaje, antes de gastar batería del Bebop |

---

## 7. Qué cambia en el manuscrito (para Javier, no se toca el `.tex`)

| Dónde | Cambio |
|---|---|
| l. 909 | la cripto pasa del firmware a un par de proxies en el enlace |
| `tab:security_goals` · *Payload confidentiality* | de «Not achieved» a lo que muestren T4 y C10 |
| `tab:security_goals` · *Data-plane integrity* | firma por sentido, **exigida** por el receptor |
| `tab:security_goals` · *Replay resistance* | `ts` estrictamente creciente por sentido, con el coste de reordenamiento medido en C11 |
| l. 1746 | «command injection prevented» **solo si** C11 (I1–I5) sale como se espera |
| cifrado | quitar AES-CTR (si se confirma H3); no llamarlo AEAD (§4.3) |
| l. 1529 | «no payload expansion beyond the existing MAVLink frame/signing overhead» sigue siendo cierto: son 13 B de firma y nada más |

## 8. Abierto

- H3 (retirar AES-CTR): confirmar.
- Umbrales de éxito de C5: en `PLAN_CAMPANA.md` §3, **se firman antes de medir**.
