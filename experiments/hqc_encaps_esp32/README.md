# Encapsulación de HQC-128 en hardware embebido real (ESP32 / Xtensa LX6)

**Por qué existe.** Proyecto hermano de
[`../hqc_encaps_pico/`](../hqc_encaps_pico/README.md) (RP2040, Cortex-M0+, 57,3 ms
medido). Ese README explica por qué en su momento se eligió el Pico y no el ESP32 ("no
hace falta duplicar el experimento"). Lo que cambió: el 2026-09-22 salió una pregunta más
específica — el mecanismo real de contención con el planificador de ArduCopter
(`subsec:realtime_control`, ver `../sitl_realtime/README.md`) compara el presupuesto de
550 µs de `update_send` contra dos puntos medidos que bracketean el Cortex-A9 real del
Bebop (no medido): 167,6 µs en x86 (cabe) y 57,3 ms en el RP2040 (excede ~104×). El rango
entre esos dos extremos es enorme. La ESP32 (Xtensa LX6, **con caché**, 240 MHz, más
cercana arquitectónicamente a un núcleo móvil moderno que el RP2040) da un **tercer punto
real**, no una simulación, que puede acotar ese rango de forma más fina — ver
`../../08_cierre/` para la conversación completa del 2026-09-22 sobre por qué no se puede
simular el Cortex-A9 directamente (QEMU es funcional, no cronométrico; gem5 sería
correcto pero necesita días y una calibración contra hardware real que no tenemos).

## Qué mide y qué NO mide (igual disciplina que el proyecto de la Pico)

- **Mide:** `PQCLEAN_HQC128_CLEAN_crypto_kem_enc()` — la encapsulación, con la misma
  implementación de referencia PQClean sin modificar, corriendo sobre ESP-IDF/FreeRTOS.
  Se reporta en **microsegundos** vía `esp_timer_get_time()` (temporizador de hardware,
  resolución de 1 µs).
- **No mide** la keypair (una sola vez, informativo — el FC no genera pares efímeros en
  este diseño, eso lo hace la GCS) ni la decapsulación (tampoco es del FC).
- **No es una medida de energía.** Solo tiempo de cómputo.
- **Diferencia de entropía con la Pico:** la ESP32 tiene un generador de números
  aleatorios **por hardware** real (`esp_fill_random()`), a diferencia del PRNG por
  software que usa la Pico (`pico_rand`, porque el RP2040 no trae TRNG dedicado) — un
  punto a favor de este banco, aunque no es lo que se está midiendo.

## Estructura

```
CMakeLists.txt          -- proyecto ESP-IDF de nivel superior
main/
  CMakeLists.txt        -- registra el componente, referencia directa a la fuente PQClean
                           del extracto del fork (02_repo/...), sin copiarla
  main.c                -- misma metodología que hqc_encaps_pico/main.c: keypair una vez,
                           N_MUESTRAS=500 encapsulaciones cronometradas, resumen +
                           volcado CSV
  randombytes_esp32.c   -- randombytes() usando esp_fill_random() (TRNG de hardware) --
                           NO es el randombytes_linux.c auditado en gap_analysis.md (A8),
                           es nuevo, solo para este banco de pruebas
```

## Cómo compilar y flashear

Toolchain oficial de Espressif (ESP-IDF), clonado directo, no por AUR/pacman -- misma
lección que el toolchain ARM del Bebop y el SDK de la Pico:

```bash
mkdir -p ~/toolchains && cd ~/toolchains
git clone --depth 1 --recursive -b release/v5.3 https://github.com/espressif/esp-idf.git
cd esp-idf && ./install.sh esp32   # descarga el compilador Xtensa precompilado, no lo compila
. ./export.sh                      # exporta idf.py al PATH de esta terminal
```

Build, flasheo y monitor (la placa aparece como `/dev/ttyUSB0`, chip CH340 -- el usuario
ya está en el grupo `uucp`, no hace falta sudo):

```bash
cd experiments/hqc_encaps_esp32
idf.py set-target esp32     # ajustar si el chip real es esp32s3/esp32c3/etc.
idf.py -p /dev/ttyUSB0 build flash monitor
```

`Ctrl+]` sale del monitor. Guardar la salida completa (redirigir `idf.py monitor` a un
archivo, o usar `idf.py -p /dev/ttyUSB0 monitor | tee resultados/captura_YYYY-MM-DD.log`)
para archivar los datos crudos igual que se hizo con la Pico.

## Estado — 2026-09-22

**Corrido en la placa física y medido de punta a punta.** Chip confirmado por
`esptool.py chip_id`: **ESP32-D0WD-V3** (rev. v3.0), dual-core, con caché, reloj de CPU
efectivo **160 MHz** (no se subió a los 240 MHz máximos del chip — configuración por
defecto, igual que la Pico no tocó su reloj de 125 MHz; queda como posible mejora futura,
no como parte de esta medición). 500 muestras de encapsulación de HQC-128 (PQClean,
referencia "clean", sin modificar).

### Resultado (microsegundos, N=500)

| Métrica | Valor |
|---|---|
| Media | 49 265,5 |
| p50 | 49 285 |
| p95 | 49 407 |
| Min / Max | 48 800 / 49 487 |
| Keypair (informativo, una sola vez) | 17 279 |

**Volcado CSV archivado:**
[`resultados/captura_serie_2026-09-22.log`](resultados/captura_serie_2026-09-22.log)
(salida completa del monitor serie, incluye las 500 muestras individuales sin editar).

### Dos fallos reales encontrados y corregidos en el camino (documentados porque son
### instructivos, no porque sean notables para el manuscrito)

1. **"Double exception" al entrar a `crypto_kem_keypair()`.** El stack por defecto de la
   tarea principal de ESP-IDF (`CONFIG_ESP_MAIN_TASK_STACK_SIZE=3584`, 3,5 KiB) es
   insuficiente para los buffers internos de la implementación de referencia de HQC-128
   (matrices/FFT). Se subió a 32 KiB en `sdkconfig.defaults` — generoso frente a los
   ~167 KiB de DRAM libre en esta placa. Sin esto, el firmware crasheaba dentro de un
   `memset` de la propia librería, antes de completar ni una sola operación.
2. **Panic del *idle task* del Task Watchdog Timer, en bucle de reinicio, antes incluso
   de imprimir el primer mensaje.** Se rastreó por dirección de retorno
   (`xtensa-esp32-elf-addr2line`) hasta `esp_task_wdt_reset()`/`idle_hook_cb` — no era
   código nuestro ni de PQClean. `esptool` había avisado de un cristal de 41,01 MHz
   detectado (fuera de los 40 MHz nominales) al conectar por primera vez, compatible con
   una placa clon con tolerancia de cristal floja, que corrompía el chequeo del
   watchdog del *idle task*. Se desactivó `CONFIG_ESP_TASK_WDT_INIT` — no afecta la
   medición (que usa `esp_timer_get_time()`, un reloj de hardware independiente), solo
   quita una herramienta de diagnóstico de tareas colgadas que no aporta nada a un
   binario de un solo experimento.

### Lectura, con cuidado de no sobre-interpretar

- **Esto es medido**, no inferido: ESP32 (Xtensa LX6, 160 MHz, con caché) tarda ~49,3 ms
  (p50) en la misma operación que el RP2040 (Cortex-M0+, 125 MHz, sin caché) tardó
  57,3 ms. Es decir, un núcleo con caché y reloj más alto es **solo ~14% más rápido**, no
  un orden de magnitud — la implementación de referencia PQClean no está optimizada para
  ninguna de las dos arquitecturas, así que el diferencial de hardware casi no se nota
  frente al costo fijo del algoritmo sin optimizar (ver la discusión de
  `kim2025hqc_cortexm4`/`Aissaoui2024OptimizedHQC` ya citada en el manuscrito).
- **Tercer punto real que acota el rango del Cortex-A9 del Bebop (no medido):** x86
  167,6 µs · ESP32 49,3 ms · RP2040 57,3 ms. El Cortex-A9 sigue sin medirse, pero ahora
  hay dos puntos independientes de microcontrolador (arquitecturas distintas, Xtensa y
  ARM) que coinciden en el mismo orden de magnitud (decenas de milisegundos) para la
  misma implementación sin optimizar — eso hace más creíble que ese orden de magnitud sea
  representativo de "hardware embebido real sin caché de datos ni implementación
  optimizada", más allá de la arquitectura específica.

### Pendiente si se decide citar esto en el manuscrito

- [ ] Confirmar con Javier si se inserta como tercer punto en el mismo párrafo de
      `subsec:realtime_control` que ya tiene el dato de la Pico, o si se dejar como
      material de apoyo en el repositorio.
