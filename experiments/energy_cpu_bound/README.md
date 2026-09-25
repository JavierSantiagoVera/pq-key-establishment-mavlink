# Cota superior de energía por ciclos de CPU (causa C4)

**Qué es:** la acción #2 que pide
[`../energy_reanalysis/FORENSICS_energia.md`](../energy_reanalysis/FORENSICS_energia.md)
tras retirar la tabla de energía en reposo (que no es rescatable con estadística): *"una
cota superior analítica derivada de conteo de ciclos de CPU por operación, medible por
microbenchmark, sin hardware de vuelo"*. `benchmark_cpu.cpp` mide el costo de SHA-256,
HMAC-SHA256, HKDF y ChaCha20 — las cuatro primitivas reales de
[`../crypto_vectors/`](../crypto_vectors/) — sobre tamaños de payload de MAVLink.

**Actualizado 2026-09-21:** se agregó una sección de **HQC-128 (PQClean, referencia
"clean", sin modificar)** al mismo binario — encapsulación aislada, la operación que el
FC sí hace en este diseño (la decapsulación es de la GCS, ver
[`../hqc_encaps_pico/README.md`](../hqc_encaps_pico/README.md), que hace lo mismo en un
Raspberry Pi Pico bare-metal). Esta versión corre sobre Linux (x86 de referencia, o el
ARM del propio Bebop al cross-compilar) — mismo patrón, plataforma distinta. Fuente
nueva: `randombytes_bench.c` (implementación de `randombytes()` solo para este banco de
pruebas, **no** el `randombytes_linux.c` auditado en `gap_analysis.md` A8 ni su parche en
`../rng_patch/` — no lo reemplaza ni lo valida).

**No depende del Bebop ni de que vuele:** es la razón por la que se hizo hoy sin batería.

## Qué mide, y por qué esos tamaños

| Tamaño | Por qué |
|---|---|
| 9 B | `HEARTBEAT` |
| 33 B | `COMMAND_LONG` |
| 64 B | tamaño medio, y un bloque exacto de ChaCha20/SHA-256 |
| 255 B | `MAVLINK_MAX_PAYLOAD_LEN` — el payload máximo de un solo frame MAVLink v2 |
| 1024 B | más allá de un frame — referencia de escalado, no un tamaño real de MAVLink |

## ⚠️ Lo más importante: dónde corre esto y qué NO significa

**Corre en el x86 del portátil (Ryzen), no en el ARM Cortex-A9 del Bebop.** Los números de
esta corrida **no son la cifra que va al artículo** — son:

1. Una **validación del método**: el arnés junta, mide con percentiles (misma disciplina
   que `arnes_baseline.py`) y compara primitivas, antes de gastar tiempo corriéndolo en el
   Bebop.
2. Un **costo relativo entre primitivas** (cuánto más cuesta HKDF que SHA-256, etc.), que
   no debería cambiar de orden de magnitud entre arquitecturas para primitivas sin
   aceleración por hardware — pero **la cifra absoluta en ns/ciclos sí puede cambiar
   mucho** entre un Ryzen de escritorio y un Cortex-A9 de 2013.

**Medido, no inferido:** todo lo de esta corrida. **Pendiente de medir donde importa:**
lo mismo, corriendo en el Bebop.

## Uso

```bash
cd experiments/energy_cpu_bound
HQC=../../firmware-fork/libraries/AP_KEM/vendor/pqclean/crypto_kem/hqc-128/clean
COMMON=../../firmware-fork/libraries/AP_KEM/vendor/pqclean/common

gcc -std=c11 -O2 -c "$COMMON/sha2.c" -o sha2.o
gcc -std=c11 -O2 -c "$COMMON/fips202.c" -o fips202.o
gcc -std=c11 -O2 -I"$COMMON" -c randombytes_bench.c -o randombytes_bench.o
for f in code fft gf2x gf2x_sparse gf hqc kem parsing reed_muller reed_solomon shake_ds shake_prng vector vector_sparse; do
  gcc -std=c11 -O2 -I"$HQC" -I"$COMMON" -c "$HQC/$f.c" -o "hqc_$f.o"
done

g++ -std=c++17 -O2 -c ../crypto_vectors/kemtls_primitives.cpp -o kemtls_primitives.o
g++ -std=c++17 -O2 -c ../crypto_vectors/chacha20.c -o chacha20.o
g++ -std=c++17 -Wall -Wextra -O2 -I"$HQC" -c benchmark_cpu.cpp -o benchmark_cpu.o

g++ -O2 -o benchmark_cpu sha2.o kemtls_primitives.o chacha20.o benchmark_cpu.o fips202.o randombytes_bench.o hqc_*.o
./benchmark_cpu 20000     # n de muestras por punto para las primitivas simetricas (default 20000);
                          # la seccion de HQC se limita sola a max 2000 (es mucho mas cara por llamada)
```

## Resultado de la corrida del 2026-09-17 (x86, n=5000, referencia — NO citar en el artículo)

| Primitiva | 9 B | 33 B | 64 B | 255 B | 1024 B |
|---|---|---|---|---|---|
| SHA-256 (p50, ns) | 387 | 388 | 716 | 1548 | 4952 |
| HMAC-SHA256 (p50, ns) | 1334 | 1322 | 1621 | 2484 | 5811 |
| HKDF, extract+expand (p50, ns) | 2641 | 2603 | 2919 | 3792 | 7127 |
| ChaCha20 (p50, ns) | 290 | 301 | 315 | 1213 | 4780 |

Cota superior por mensaje tipo `COMMAND_LONG` (33 B), las cuatro primitivas encadenadas
una vez: **p50 = 4590 ns, p95 = 4621 ns** — en el Ryzen del portátil, no en el Bebop.

### HQC-128, corrida de validación del 2026-09-21 (x86, n=2000, referencia — NO citar)

| | Tiempo |
|---|---|
| Keypair (una vez) | 82,9 µs |
| Encapsulación, p50 | 167,6 µs |
| Encapsulación, p95 | 241,9 µs |

Sirve para confirmar que el método funciona end-to-end (enlaza, corre, produce
percentiles coherentes) antes de gastar tiempo en el Bebop — no es la cifra del
artículo. Para contraste: la misma operación en un Raspberry Pi Pico (RP2040,
Cortex-M0+, bare-metal) tardó 57,3 ms de mediana — unas 342 veces más lento que este
x86 de escritorio, coherente con la diferencia de frecuencia de reloj y de
arquitectura (superescalar de varios GHz vs. un núcleo simple de 125 MHz). Ver
[`../hqc_encaps_pico/README.md`](../hqc_encaps_pico/README.md).

## Para correrlo en el Bebop — el compilador cruzado ya está listo (2026-09-17)

El paquete de Arch (`gcc-arm-none-eabi`) es para microcontroladores, no sirve para el Linux
del Bebop — ya lo anotaba `../../08_cierre/HANDOFF_PORTATIL.md` §5. El paquete AUR
`arm-linux-gnueabihf-gcc-bin` **no sirve**: pese a decir "precompiled", sus dependencias
resuelven a paquetes que compilan GCC desde cero (clonan el repositorio git completo de
GCC) — se abortó a los pocos minutos, no se instaló nada.

**Lo que sí funciona:** el toolchain oficial de ARM, descargado directo (sin AUR) y
extraído en `~/toolchains/` (fuera del repo, no se versiona):

```bash
curl -fSL -o /tmp/arm-gnu-toolchain.tar.xz \
    "https://developer.arm.com/-/media/Files/downloads/gnu/15.2.rel1/binrel/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-linux-gnueabihf.tar.xz"
mkdir -p ~/toolchains && tar -xf /tmp/arm-gnu-toolchain.tar.xz -C ~/toolchains
export PATH="$HOME/toolchains/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-linux-gnueabihf/bin:$PATH"
```

Ya probado el 2026-09-17 (y reconfirmado el 2026-09-21 tras agregar HQC-128): compila el
proyecto completo sin errores (solo notas de ABI de GCC, informativas) y produce un ELF de
32 bits ARM, estático, válido:

```bash
cd experiments/energy_cpu_bound
export PATH="$HOME/toolchains/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-linux-gnueabihf/bin:$PATH"
HQC=../../firmware-fork/libraries/AP_KEM/vendor/pqclean/crypto_kem/hqc-128/clean
COMMON=../../firmware-fork/libraries/AP_KEM/vendor/pqclean/common

arm-none-linux-gnueabihf-gcc -std=c11 -O2 -static -c "$COMMON/sha2.c" -o sha2_arm.o
arm-none-linux-gnueabihf-gcc -std=c11 -O2 -static -c "$COMMON/fips202.c" -o fips202_arm.o
arm-none-linux-gnueabihf-gcc -std=c11 -O2 -static -I"$COMMON" -c randombytes_bench.c -o randombytes_bench_arm.o
for f in code fft gf2x gf2x_sparse gf hqc kem parsing reed_muller reed_solomon shake_ds shake_prng vector vector_sparse; do
  arm-none-linux-gnueabihf-gcc -std=c11 -O2 -static -I"$HQC" -I"$COMMON" -c "$HQC/$f.c" -o "hqc_${f}_arm.o"
done

arm-none-linux-gnueabihf-g++ -std=c++17 -O2 -static -c ../crypto_vectors/kemtls_primitives.cpp -o kemtls_primitives_arm.o
arm-none-linux-gnueabihf-g++ -std=c++17 -O2 -static -c ../crypto_vectors/chacha20.c -o chacha20_arm.o
arm-none-linux-gnueabihf-g++ -std=c++17 -Wall -Wextra -O2 -static -I"$HQC" -c benchmark_cpu.cpp -o benchmark_cpu_arm.o

arm-none-linux-gnueabihf-g++ -static -O2 -o benchmark_cpu_arm \
  sha2_arm.o kemtls_primitives_arm.o chacha20_arm.o benchmark_cpu_arm.o fips202_arm.o randombytes_bench_arm.o hqc_*_arm.o
# copiar benchmark_cpu_arm al Bebop (mismo mecanismo de experiments/campana_bebop/,
# por FTP o el que se decida ese día) y correrlo por telnet.
```

**Probado con QEMU el 2026-09-17 y 2026-09-21:** `qemu-arm-static ./benchmark_cpu_arm 20`
corre de punta a punta sin errores, incluida la sección nueva de HQC-128 — el binario es
funcionalmente correcto y va a andar en el Bebop. **Los tiempos de esa corrida NO sirven
como referencia de ningún tipo:** QEMU en modo usuario traduce instrucción por
instrucción, no es fiel a ciclos de reloj reales — ni siquiera vale como comparación
relativa entre primitivas, a diferencia de la corrida en x86 real de más arriba. Solo
confirma que el binario corre; la cifra de costo real sigue esperando el Bebop con
alimentación.

## Estado — 2026-09-21

**Listo para correr en el Bebop en cuanto haya alimentación.** Falta únicamente copiar
`benchmark_cpu_arm` al dron (FTP/telnet, mismo mecanismo que `../campana_bebop/`) y
ejecutarlo — ni la compilación ni la validación funcional quedan pendientes.
