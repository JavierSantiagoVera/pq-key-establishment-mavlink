# Mecanismo de contención con el planificador, confirmado en ArduCopter real (ESP32)

**Qué es:** continuación de `../sitl_realtime/` — ahí se identificó por lectura de código
(no medición) que `start_encap()` bloquea dentro de `GCS_MAVLINK::update_send()`, una
tarea del planificador cooperativo de ArduCopter con 550 µs de presupuesto a 400 Hz. Los
dos intentos de verlo en vivo en SITL fallaron (inestabilidad ya documentada). Este
experimento lo confirma en **hardware real**, aprovechando que ArduPilot tiene soporte
nativo para ESP32 (`libraries/AP_HAL_ESP32/`, boards `esp32diy`/`esp32buzz`/`esp32empty`/
`esp32icarus`/`esp32s3devkit`) — descubierto el 2026-09-22, no se sabía hasta ese momento.

**Importante:** esto NO es la extensión HQC del fork corriendo en la ESP32. Es
**ArduCopter stock** (`~/ardupilot`, sin el fork) con una tarea de sondeo (`hqc_realtime_probe`,
la misma de `sitl_realtime/`) agregada a la tabla del planificador, en el mismo hueco de
presupuesto (550 µs/400 Hz) que ocupa `update_send`. Confirma el mecanismo, no mide la
extensión HQC en sí.

## Por qué ESP32 y no otro target

- Usa exactamente el mismo ESP-IDF (`release/v5.3`) ya instalado para
  `../hqc_encaps_esp32/` — sin toolchain nuevo.
- `esp32empty` es un target pensado para placas sin ningún sensor conectado
  (`HAL_INS_DEFAULT HAL_INS_NONE`) — coincide exactamente con la placa física disponible
  (sin IMU, sin GPS, sin brújula), evitando que el arranque se quede reintentando
  inicialización de sensores.
- **No es el Cortex-A9 del Bebop ni su HAL Linux** — usa `AP_HAL_ESP32`, un HAL y modelo
  de hilos distinto al `AP_HAL_Linux` real del Bebop. Confirma el mecanismo
  (`AP_Scheduler`, presupuesto por tarea, detección de sobrepaso), no reproduce el
  hardware objetivo.

## Cómo se hizo

1. Se agregó `hqc_realtime_probe()` a `~/ardupilot/ArduCopter/{Copter.h,Copter.cpp}`
   (mismo código que `sitl_realtime/README.md`), con la duración del busy-wait fijada por
   `#define HQC_PROBE_BUSY_US`, recompilada entre corridas.
2. Toolchain: `export IDF_PATH=~/toolchains/esp-idf && source ~/toolchains/esp-idf/export.sh`
   (mismo ESP-IDF que el proyecto de cripto). Faltaban `empy` y `pexpect`/`pymavlink` en el
   entorno virtual **de ESP-IDF** específicamente (distinto del entorno de usuario donde ya
   estaban instalados) — se instalaron ahí también.
3. Build y flasheo:
   ```bash
   cd ~/ardupilot
   ./waf configure --board=esp32empty
   ./waf copter
   ESPPORT=/dev/ttyUSB0 ESPBAUD=460800 ./waf copter --upload
   ```
4. **Truco necesario para leer la consola/MAVLink por el mismo puerto USB (CH340):**
   abrir el puerto con `pyserial` deja la placa detenida (DTR/RTS en el estado por
   defecto de `pyserial` sostienen el circuito de auto-reset del ESP32 en un estado que no
   deja correr la aplicación). Hay que forzar manualmente `dtr=False`, pulso de
   `rts=True` y volver a `rts=False`, **antes** de esperar el primer heartbeat.
5. El canal necesita ver tráfico saliente nuestro antes de considerarse "activo" y
   transmitir `STATUSTEXT` — se manda un heartbeat propio cada segundo mientras se
   escucha (mismo hallazgo que en `sitl_realtime/`, pero esta vez sí funcionó).

## Resultado — 2026-09-22

### Corrida 1: HQC_PROBE_BUSY_US = 550 (el borde exacto del presupuesto)

| n | `dur_us` | `long_running` | `loop_hz` |
|---|---|---|---|
| 1 | 550 | 0 | 100.0 |
| 101 | 550 | 1 | 99.8 |
| 601 | 550 | 1 | 99.9 |

El contador de sobrepaso (`AP::scheduler().perf_info.get_num_long_running()`) ya marca
al menos un evento apenas empieza a correr la sonda, justo en el borde del presupuesto.

### Corrida 2: HQC_PROBE_BUSY_US = 57300 (la cifra real medida en microcontroladores)

| n | `dur_us` | `long_running` | `extra_loop_us` | `loop_hz` |
|---|---|---|---|---|
| 1 | 57301 | 0 | 0 | 100.0 |
| 6 | 57300 | 4 | 200 | 100.0 |
| 61 | 57300 | 59 | 5000 | 95.1 |
| 311 | 57300 | 309 | 5000 | 95.1 |

Tres cosas que confirma, todas en hardware real:
1. **`long_running` crece prácticamente 1:1 con cada llamada** — casi todas las
   invocaciones se marcan como pasadas de presupuesto.
2. **`extra_loop_us` se satura exactamente en 5000** — el mismo techo que
   `AP_Scheduler.cpp` codifica (`extra_loop_us = MIN(extra_loop_us+100U, 5000U)`),
   confirmado en ejecución, no solo leído en el código.
3. **`loop_hz` cae de 100,0 a 95,1 Hz y se mantiene ahí**, sostenido durante toda la
   corrida (300+ llamadas, >30 s) — una degradación medible y persistente de la tasa del
   lazo principal, causada por una sola tarea bloqueante.

Capturas completas (STATUSTEXT crudos, con ruido de `BAD_DATA` por la consola de texto
plano compartiendo el mismo UART) en `resultados/`.

## Qué significa esto para el manuscrito

Cambia la naturaleza de la afirmación en `subsec:realtime_control`: de "riesgo
arquitectónico identificado por el presupuesto declarado del planificador, no una falla
medida" a **"mecanismo confirmado en ejecución, en hardware real, aunque no en el
Cortex-A9/HAL Linux del Bebop"**. Se aplicó al `.tex` el 2026-09-22 — ver
`01_manuscript/current_cas-sc/CAMBIOS_REDACCION.md`.

## Qué NO cierra

- No es el Cortex-A9 del Bebop, ni su `AP_HAL_Linux` (hilos con `SCHED_FIFO` y
  prioridades fijas, distinto del modelo de hilos de `AP_HAL_ESP32`).
- No incluye la extensión HQC del fork — es ArduCopter stock con una tarea de sondeo.
- `~/ardupilot` se revirtió limpio después (`git checkout -- ArduCopter/Copter.h
  ArduCopter/Copter.cpp`) — es una herramienta externa, no se deja modificada.

## Si se quiere ir más lejos

Un Raspberry Pi (o cualquier placa Linux/ARM real) correría literalmente el mismo
`AP_HAL_Linux` que usa el Bebop — sería un paso más fiel que la ESP32 para este mismo
experimento. Ver la discusión de "qué tan lejos simular el hardware del Bebop" en
`08_cierre/` (conversación del 2026-09-22) para el análisis completo de opciones.
