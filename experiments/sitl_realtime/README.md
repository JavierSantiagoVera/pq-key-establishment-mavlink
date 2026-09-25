# C5, mecanismo de contención con el planificador — 2026-09-22

**Qué responde:** si "no se puede simular o estimar el tiempo real con el Pico o de más" —
sí, mejor: no hace falta simular nada, el mecanismo se puede verificar leyendo el código
real de ArduPilot que este proyecto extiende. No depende del Bebop ni de ningún
microcontrolador.

## El hallazgo (medido = lectura directa de código real, no una medición en hardware)

- `libraries/GCS_MAVLink/GCS_KEMTLS.cpp:540` (`HqcSession::start_encap()`) llama a
  `ap_kem_enc()` de forma **síncrona y bloqueante**.
- `libraries/AP_KEM/ap_kem.cpp:17-20`: `ap_kem_enc()` es un envoltorio delgado sobre
  `PQCLEAN_HQC128_CLEAN_crypto_kem_enc()` — la misma función medida en
  `experiments/energy_cpu_bound/` (x86, 167,6 µs) y en
  `experiments/hqc_encaps_pico/` (RP2040, 57,3 ms).
- `libraries/GCS_MAVLink/GCS_Common.cpp:1568`: el tick del handshake (`hqc_.tick()`) se
  llama desde `GCS_MAVLINK::update_send()`.
- `~/ardupilot/ArduCopter/Copter.cpp:208`: `update_send` es una tarea de la tabla del
  planificador de ArduCopter — cooperativo, un solo hilo — con **400 Hz y 550 µs de
  presupuesto** (`SCHED_TASK_CLASS(GCS, ..., update_send, 400, 550, 105)`), compartiendo
  el mismo ciclo que el control de actitud y la mezcla de motores.

Conclusión (aritmética sobre los dos números reales que ya se tenían, sin combinarlos con
nada nuevo): 167,6 µs (x86) cabe en el presupuesto; 57,3 ms (RP2040 Cortex-M0+) lo excede
en ~2 órdenes de magnitud. No se sabe el número del Cortex-A9 real del Bebop, pero un
núcleo móvil de 2013 está arquitectónicamente mucho más cerca del extremo lento que del
x86 de escritorio. Insertado en el manuscrito, `subsec:realtime_control`, como riesgo
arquitectónico identificado por código, no como fallo medido.

## Lo que se intentó, y por qué se dejó (2026-09-22)

Se intentó ir más allá: en vez de solo leer el código, correr una tarea de sondeo
(`hqc_realtime_probe`, un busy-wait calibrado a duraciones reales: 550 µs, 2500 µs,
57 300 µs) en el mismo hueco del planificador de ArduCopter (`Copter.cpp`, prioridad 106,
justo después de `update_send`) dentro de SITL, y leer `AP::scheduler().perf_info` para
ver si el detector de sobrepaso real del planificador se disparaba.

- Se agregó la función y la entrada de la tabla en `~/ardupilot` (herramienta externa,
  no el fork — igual que `parche_canal0.patch` en `signing_policy/`).
- Compiló sin errores (`./waf copter`, tras instalar `empy==3.3.4` vía
  `pip install --user --break-system-packages`, que faltaba en este portátil — la versión
  del repo oficial de Arch, `python-empy 4.2.1`, es incompatible con el `mavgen` de
  ArduPilot).
- Al correr SITL para capturar el mensaje `STATUSTEXT` de la sonda, se repitió el mismo
  problema de inestabilidad **ya documentado y sin resolver** en
  `~/.claude/.../memory/project_cierre_taes_objetivos.md` §"Como dejar SITL corriendo de
  verdad" (la saga "SITL se muere sola" del 2026-09-17/18): el canal primario (puerto
  5760) se desconecta (`EOF on TCP socket`) apenas se abre, de forma repetible, sin volver
  a levantarse por sí solo. Esa memoria ya concluye que la causa real nunca se encontró, y
  que lo único que funcionó de forma confiable fue que **Javier** sostenga la consola de
  MAVProxy a mano en su propia terminal.
- **Se decidió no seguir insistiendo por script** (mismo criterio que esa memoria: "no
  forzar más esta vía sin la configuración original"), revertir el cambio en
  `~/ardupilot` (`git checkout -- ArduCopter/Copter.h ArduCopter/Copter.cpp`, confirmado
  limpio) y quedarse con el hallazgo de código, que ya es suficiente para lo que dice el
  manuscrito (no afirma haber observado el sobrepaso en vivo, afirma el riesgo
  arquitectónico identificado por lectura de código real).

## Segundo intento (2026-09-22, más tarde) — con Javier sosteniendo la consola

Con Javier sosteniendo `sim_vehicle.py --console` a mano en su propia terminal
(la vía que la primera vez sí funcionó, requirió corregir dos cosas primero:
`source ~/venv-ardupilot/bin/activate` para que exista `mavproxy.py`, y
`export SITL_RITW_TERMINAL="setsid"` para evitar que `run_in_terminal_window.sh`
intentara abrir `gnome-terminal`, que fallaba con "Failed to get screen from object
path" en este entorno sin sesión gráfica completa), se reintentó la sonda del
planificador **sin tocar la sesión de Javier**: se agregó `hqc_realtime_probe` de nuevo
en `~/ardupilot`, se recompiló, y se lanzó una **segunda instancia SITL independiente**
(`-I1`, puertos 5770/5772/5773 en vez de 5760/5762/5763) para no arriesgar la conexión
que Javier sostenía.

**Resultado:** la instancia 1 arrancó bien (confirmado por heartbeat en el puerto
primario 5770), pero el puerto secundario (5772, donde vive la sonda) nunca entregó ni
un solo mensaje `HQCPROBE`, ni siquiera su propio heartbeat periódico, pese a:
- Enviar un heartbeat propio hacia ese puerto antes de esperar uno (para "activar" el
  canal, como exige `GCS_MAVLINK` antes de transmitir a un cliente).
- Confirmar que `SERIAL1_PROTOCOL` sí es `MAVLink2` por defecto
  (`AP_SerialManager.cpp:48`), no un puerto sin protocolo.

No se identificó la causa raíz exacta (posiblemente relacionado con cómo SITL decide
qué canales son "activos" para el broadcast de `gcs().send_text()`, o con timing de
arranque). **Se decidió parar acá** (mismo criterio que la primera vez: no forzar una
vía que ya consumió varios intentos, cuando el hallazgo de código ya es suficiente para
el manuscrito) y se revirtió `~/ardupilot` limpio otra vez
(`git checkout -- ArduCopter/Copter.h ArduCopter/Copter.cpp`, confirmado, más un
`./waf copter` extra para que el binario en disco vuelva a coincidir con el código
stock). **La sesión de Javier (instancia 0) nunca se tocó** — se verificó viva e
intacta antes y después de este intento.

## Si se quiere retomar esto

La función de sondeo y el diseño del experimento (barrido 550 µs / 2500 µs / 57 300 µs,
lectura de `perf_info.get_num_long_running()` y `get_extra_loop_us()`) están descritos
arriba y son baratos de re-crear. Lo que hace falta es correr `sim_vehicle.py --console`
**a mano**, en una terminal sostenida por una persona (no por reconexiones automáticas de
un script), como ya funcionó antes para otros hallazgos de este proyecto
(`signing_policy/HALLAZGO_firma_no_exigida.md`).
