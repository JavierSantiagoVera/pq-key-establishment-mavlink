# Cuánto se puede acercar la simulación al Cortex-A9 del Bebop sin el hardware físico

**Pregunta que responde:** después de confirmar el mecanismo del planificador en ESP32
(`../esp32_realtime/`), Javier pidió explorar "qué tan lejos" se puede llegar simulando
el hardware real del Bebop — el escalón siguiente sería usar el mismo HAL Linux del
Bebop (`AP_HAL_Linux`), no el de la ESP32 (`AP_HAL_ESP32`).

**Resumen del veredicto:** se llegó mucho más lejos de lo esperado (kernel Linux real +
Cortex-A9 emulado + ArduCopter compilado con el hwdef **exacto** `bebop`, con MAVLink
real funcionando), pero se topó con una condición de carrera dependiente de timing entre
hilos que no se pudo resolver en el tiempo disponible. **No se llegó a confirmar la
sonda del planificador aquí** — esa confirmación ya la tenemos, y es válida, desde
`../esp32_realtime/`. Este experimento vale por otra cosa: encontró y documentó con
precisión tres defectos reales en el driver Linux específico del Bebop
(`RCOutput_Bebop`, `PWM_Sysfs`) que solo se manifiestan cuando el hardware propietario
de Parrot no está presente.

## Qué se armó (todo desde cero, sin descargas de terceros no verificables)

1. **Kernel Linux 6.6.y**, clonado oficial (`git.kernel.org`, rama `linux-6.6.y`),
   compilado con `vexpress_defconfig` (el defconfig real de mainline para esta clase de
   placa) usando el mismo cross-compiler ARM ya instalado
   (`arm-none-linux-gnueabihf-gcc`). Produce `zImage` + `vexpress-v2p-ca9.dtb`.
2. **busybox**, clonado oficial (`git.busybox.net`), compilado estático para ARM.
3. **initramfs mínimo**: busybox + un script `init` que monta `/proc`, `/sys`, `/dev`,
   configura red, y arranca el binario de prueba.
4. **`qemu-system-arm -M vexpress-a9 -cpu cortex-a9`**: la única máquina de QEMU que
   modela una placa Cortex-A9 real (no genérica) con dispositivos concretos (UART, red,
   flash).
5. **ArduCopter compilado con `--board=bebop`** (el hwdef real de `AP_HAL_Linux`, el
   mismo código que corre en el Bebop físico) — requirió un *shim* de symlinks
   (`arm-linux-gnueabihf-*` → nuestro `arm-none-linux-gnueabihf-*`) porque ArduPilot
   busca ese prefijo exacto de toolchain.

Instrucciones completas de compilación en el historial de comandos de la sesión — si se
retoma esto, lo más laborioso (kernel, busybox, shim del toolchain) ya está listo en
`~/toolchains/linux-vexpress/`, `~/toolchains/busybox-arm/`,
`~/toolchains/arm-linux-gnueabihf-shim/`.

## Los tres defectos reales encontrados (con precisión de línea de código, vía `gdbserver` ARM real)

Todos comparten la misma causa raíz: **el chip I2C/hardware propietario de Parrot no
existe** en este entorno, así que `hal.i2c_mgr->get_device(...)` devuelve un puntero
nulo o el `open()` de un archivo `/sys/...` falla — y el código de `AP_HAL_Linux`
específico del Bebop no siempre maneja ese caso con la misma gracia que sí tienen los
sensores genéricos (IMU/compás/baro, que reintentan en bucle sin más).

| # | Dónde | Qué pasaba | Cómo se encontró |
|---|---|---|---|
| 1 | `RCOutput_Bebop::init()` (y ocho métodos más que usan `_dev` sin verificar) | `_dev` es `nullptr` (no hay chip BLDC de motores) → desreferencia de puntero nulo → `SIGSEGV` | `gdbserver` ARM real + `arm-none-linux-gnueabihf-gdb` remoto, `bt` da la línea exacta |
| 2 | `PWM_Sysfs_Base::init()` | No existe `/sys/class/pwm/pwm_6/duty_ns` (calentador del IMU) → `AP_HAL::panic()` aborta **todo el proceso**, no solo ese subsistema | Mismo mecanismo de `gdbserver` |
| 3 | Chequeo de arranque de `AP_Baro` | Sin barómetro real, `AP_BoardConfig::in_config_error()` bloquea el vehículo en un bucle de "Config Error: fix problem then reboot" indefinido — este bucle es **paralelo** al `AP_Scheduler` normal, así que ni siquiera con la sonda agregada se vería nada mientras el error persista | Lectura de `AP_Vehicle.cpp`, confirmado en vivo |

Los tres se **parchearon temporalmente** (guardas `if (!_dev)`, degradar el `panic()` de
PWM a un aviso no fatal, y `define HAL_BARO_ALLOW_INIT_NO_BARO 1` — el mismo mecanismo
oficial que ya usa el target `esp32empty`), se verificó que cada uno destrabara el
arranque un paso más, y luego se **revirtió todo** con `git checkout` — `~/ardupilot`
quedó limpio, confirmado.

## Hasta dónde se llegó, con evidencia real

Con los tres parches activos, ArduCopter real llegó a:
- Arrancar sobre el kernel Linux real, Cortex-A9 emulado.
- Configurar red y **enviar/recibir MAVLink real** (heartbeats, TIMESYNC) por UDP desde
  el host.

Después de resolver los tres puntos de arriba, apareció un **cuarto problema**: el
proceso a veces llega a un `Segmentation fault` (visto dos veces, en puntos distintos
del código de reintento de carga de parámetros) y a veces sale limpio — el
comportamiento cambió entre correrlo normal y correrlo bajo `gdbserver` (que altera el
entrelazado de hilos), lo cual es la firma característica de una **condición de
carrera** entre hilos, no de un bug determinístico como los tres anteriores. Diagnosticar
esto con precisión requeriría instrumentación más fina (por ejemplo, `ThreadSanitizer`,
que no está disponible para este cross-compile sin más trabajo de toolchain) — se decidió
parar acá en vez de seguir cazando con retornos decrecientes.

## Por qué esto no reemplaza a la confirmación de la ESP32

`../esp32_realtime/README.md` ya tiene, con datos reales y reproducibles, la
confirmación en vivo del mecanismo del planificador (`long_running` creciendo 1:1,
`extra_loop_us` saturando en el techo de 5000 µs del propio código, `loop_hz` cayendo de
forma sostenida). Este experimento con `vexpress-a9`/`bebop` **no llegó a repetir esa
confirmación** — la condición de carrera lo impidió antes de que la sonda pudiera correr
de forma estable. Lo que sí aporta es genuino pero distinto: evidencia de que el HAL
Linux específico del Bebop tiene puntos reales, localizados con precisión, donde no
degrada con gracia ante hardware ausente — información que podría ser útil para
Nicolás si en algún momento retoma el fork y necesita adaptar ese código para pruebas
sin el hardware físico completo.

## Si se quiere retomar

1. El kernel, busybox y el shim del toolchain ya están listos, no hay que rehacerlos.
2. Los tres parches (guardas en `RCOutput_Bebop.cpp`, degradar el panic en
   `PWM_Sysfs.cpp`, `HAL_BARO_ALLOW_INIT_NO_BARO` en el hwdef) están descritos arriba
   con precisión suficiente para reaplicarlos rápido.
3. El cuarto problema (condición de carrera) necesitaría, como próximo paso razonable,
   correr bajo `strace -f` (múltiples hilos) en vez de `gdb` para no alterar tanto el
   timing, o revisar directamente el código de `Util::init()`/carga de parámetros por
   defecto en busca de una condición de carrera de inicialización conocida.
