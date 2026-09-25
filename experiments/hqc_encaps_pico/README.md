# Encapsulación de HQC-128 en hardware embebido real (Raspberry Pi Pico / RP2040)

**Por qué existe.** `01_manuscript/current_cas-sc/cas-sc-template.tex`
(`subsec:realtime_control`, párrafo "The second concerns *where* the timings were
obtained", editado 2026-09-21 — ver
`../../01_manuscript/current_cas-sc/CAMBIOS_REDACCION.md` ítem 🔴#1) dice que la cifra de
1,72 ms del artículo se midió en la GCS (x86), no en el FC, y que la pregunta que sigue
abierta es el coste de la **encapsulación** — la operación que sí hace el FC — en hardware
de autopiloto real, más constreñido que el Cortex-A9 con Linux del Bebop. Esto no depende
del Bebop ni de su batería: se puede cerrar con cualquier microcontrolador ARM de verdad.

**Por qué la Pico y no el ESP32** (que también estaba disponible): el RP2040 es
**ARM Cortex-M0+**, la misma familia que el "STM32 Cortex-M4 class part" que menciona el
manuscrito — bare-metal, sin sistema operativo, sin caché de datos. El ESP32 es Xtensa
(otra arquitectura), y aunque también serviría, no hace falta duplicar el experimento
teniendo ya la placa más representativa.

## Qué mide y qué NO mide

- **Mide:** el tiempo de `PQCLEAN_HQC128_CLEAN_crypto_kem_enc()` — la encapsulación, con la
  implementación de referencia de PQClean (la misma que usa el resto del proyecto, sin
  modificar), corriendo bare-metal en el RP2040. Se reporta en **microsegundos** (el timer
  de hardware del RP2040 tiene esa resolución), no en ciclos de instrucción — el
  Cortex-M0+ no tiene la unidad DWT que daría conteo de ciclos, así que no se finge esa
  precisión.
- **No mide** la generación de keypair (se hace una sola vez, fuera del bucle: en este
  diseño el FC no genera pares efímeros, eso lo hace la GCS — ver
  `01_manuscript/.../cas-sc-template.tex` l. ~1112) ni la decapsulación (tampoco es del FC).
- **No es una medida de energía.** Es tiempo de cómputo. Traducir esto a energía
  requeriría además medir corriente durante la operación (multímetro/shunt), que queda
  fuera de este experimento — se puede agregar después si hace falta.

## Estructura

```
CMakeLists.txt          -- build de CMake para el Pico SDK, referencia directa a la fuente
                           PQClean del extracto del fork (02_repo/...), sin copiarla
main.c                  -- keypair una vez, N_MUESTRAS encapsulaciones cronometradas,
                           imprime resumen (media/p50/p95/min/max) + volcado CSV por serie
randombytes_pico.c      -- randombytes() para RP2040 usando pico_rand (SDK oficial) --
                           NO es el randombytes_linux.c auditado en gap_analysis.md (A8),
                           es nuevo, solo para este banco de pruebas
pico_sdk_import.cmake   -- helper estándar del Pico SDK
```

## Cómo se compiló (2026-09-21)

Toolchain instalado desde los repos oficiales de Arch/CachyOS (no AUR, misma lección que
`../energy_cpu_bound/README.md` sobre el toolchain ARM del Bebop):

```bash
sudo pacman -S --needed arm-none-eabi-gcc arm-none-eabi-binutils arm-none-eabi-newlib cmake
```

Pico SDK oficial, clonado fuera del repo (no versionado), con los submódulos mínimos:

```bash
mkdir -p ~/toolchains && cd ~/toolchains
git clone --depth 1 -b master https://github.com/raspberrypi/pico-sdk.git
cd pico-sdk && git submodule update --init --depth 1 lib/tinyusb lib/mbedtls
```

Build:

```bash
cd experiments/hqc_encaps_pico
mkdir -p build && cd build
cmake -DPICO_SDK_PATH=$HOME/toolchains/pico-sdk ..
make -j"$(nproc)"
```

**Confirmado el 2026-09-21:** compila y enlaza sin errores
(`hqc_encaps_pico.elf`, `hqc_encaps_pico.uf2` generados). Un `qsort` sin `<stdlib.h>` fue
el único error real (implicit declaration), corregido.

## Cómo flashear y correr

1. Desconectar la Pico, mantener apretado el botón **BOOTSEL** y volver a conectarla por
   USB — aparece como una unidad de almacenamiento masivo `RPI-RP2`.
2. Copiar `build/hqc_encaps_pico.uf2` a esa unidad (se reinicia sola al terminar la copia).
3. Abrir una terminal serie sobre el puerto que aparezca (`/dev/ttyACM0` en este portátil,
   115200 baudios o el que autodetecte `screen`/`minicom`/`picocom`):
   ```bash
   picocom -b 115200 /dev/ttyACM0
   # o: screen /dev/ttyACM0 115200
   ```
4. El firmware espera hasta 15 s a que se abra la terminal, corre `N_MUESTRAS` (500 por
   defecto, editable en `main.c`) encapsulaciones, e imprime el resumen y el volcado CSV
   completo. Guardar la salida de la terminal a un archivo para archivar los datos crudos
   (por ejemplo, `picocom` con `--logfile`).

## Estado — 2026-09-21

**Corrido en la placa física y medido de punta a punta.** Flasheado por USB en modo
BOOTSEL, capturado por `/dev/ttyACM0` (115200 baudios efectivos vía CDC-ACM), 500
muestras de encapsulación de HQC-128 (PQClean, referencia "clean"), sin modificar el
firmware por defecto del Pico SDK (reloj a 125 MHz, no se tocó `set_sys_clock_khz`).

### Resultado (microsegundos, N=500)

| Métrica | Valor |
|---|---|
| Media | 57 258,6 |
| p50 | 57 291 |
| p95 | 57 578 |
| Min / Max | 56 424 / 58 101 |
| Keypair (informativo -- una sola vez, fuera del bucle, el FC no genera pares efímeros) | 21 064 |

**Volcado CSV archivado:** [`resultados/captura_serie_2026-09-21.log`](resultados/captura_serie_2026-09-21.log)
(salida completa de la terminal serie, incluye las 500 muestras individuales en orden de
captura, sin editar).

### Lectura, con cuidado de no sobre-interpretar

- **Esto es medido**, no inferido: el RP2040 (Cortex-M0+, 125 MHz, sin caché, bare-metal)
  corriendo la encapsulación de HQC-128 tarda ~57,3 ms (p50). Es un dato real de hardware
  de la misma familia ARM que un autopiloto STM32 típico -- no una extrapolación.
- **No es directamente comparable a la cifra de 1,72 ms del manuscrito** (l. ~1592/1611
  del `.tex`): esa cifra es un intervalo de red GCS→FINISH medido en el Ryzen 7 4800H x86
  de la GCS, no un conteo de ciclos de una operación de KEM aislada, y además es
  decapsulación (GCS), no encapsulación (FC) -- son magnitudes distintas por diseño y por
  arquitectura. Lo que sí es comparable, y es el punto: **~57 ms en hardware embebido real
  es un orden de magnitud mayor que 1,72 ms en un x86 de escritorio**, lo cual respalda
  exactamente la advertencia que ya hace el manuscrito sobre no extrapolar tiempos de un
  host de GCS a hardware de vuelo.
- **No es una cifra de energía.** Es tiempo de cómputo. No se midió corriente durante la
  operación.
- **RP2040, no STM32.** Se declara así en el manuscrito si esta cifra se cita -- es la
  familia ARM Cortex-M correcta, pero no es literalmente el chip que se nombra en el
  párrafo original. La cota es válida como "hardware embebido real, sin caché, sin
  Linux", no como "el STM32 exacto".

### Pendiente si se decide citar esto en el manuscrito

- [ ] Decidir con Javier si esta cifra reemplaza la frase "we identify this as the
      necessary next step rather than claim as a result" (l. ~1611) por un resultado real
      citado, o si se mantiene como trabajo futuro y esto queda solo como material de
      apoyo en el repositorio.
