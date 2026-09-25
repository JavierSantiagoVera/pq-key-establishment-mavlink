// Benchmark de ciclos de encapsulacion de HQC-128 (PQClean, referencia "clean") en un
// Raspberry Pi Pico (RP2040, ARM Cortex-M0+ dual-core, bare-metal, sin Linux, sin cache).
//
// Por que existe: 01_manuscript/current_cas-sc/cas-sc-template.tex (subsec:realtime_control,
// parrafo "The second concerns where the timings were obtained", editado 2026-09-21) declara
// que falta "a cycle-accurate benchmark" de la operacion que el FC SI hace (encapsulacion,
// no decapsulacion -- esa la hace la GCS) en hardware realmente constreñido, mas
// representativo de un autopiloto que el Cortex-A9 con Linux del Bebop. Esto no depende
// del Bebop ni de su bateria -- ver CAMBIOS_REDACCION.md item 🔴#1 para el contexto completo.
//
// Que mide: tiempo de PQCLEAN_HQC128_CLEAN_crypto_kem_enc() -- la funcion de encapsulacion
// -- en microsegundos, con el timer de hardware del RP2040 (time_us_64(), resolucion 1us).
// No es un contador de ciclos de instruccion (el Cortex-M0+ del RP2040 no tiene DWT), asi
// que se reporta en microsegundos, no en ciclos -- mas honesto que fingir una precision que
// el chip no tiene.
//
// Que NO mide: la keypair (se genera una sola vez, fuera del bucle de medicion, porque el
// FC de este diseño no genera pares efimeros -- eso lo hace la GCS) ni la decapsulacion
// (tampoco es del FC).

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "pico/stdlib.h"

#include "api.h"

#ifndef N_MUESTRAS
#define N_MUESTRAS 500
#endif

static uint8_t pk[PQCLEAN_HQC128_CLEAN_CRYPTO_PUBLICKEYBYTES];
static uint8_t sk[PQCLEAN_HQC128_CLEAN_CRYPTO_SECRETKEYBYTES];
static uint8_t ct[PQCLEAN_HQC128_CLEAN_CRYPTO_CIPHERTEXTBYTES];
static uint8_t ss[PQCLEAN_HQC128_CLEAN_CRYPTO_BYTES];

static uint64_t muestras_us[N_MUESTRAS];

static int comparar_u64(const void *a, const void *b) {
    uint64_t va = *(const uint64_t *)a;
    uint64_t vb = *(const uint64_t *)b;
    if (va < vb) return -1;
    if (va > vb) return 1;
    return 0;
}

int main(void) {
    stdio_init_all();

    // Esperar a que se abra una terminal serie por USB, con tope de tiempo -- si nadie
    // conecta, igual corre y los resultados solo quedan en el buffer de stdio_usb.
    uint32_t espera_ms = 0;
    while (!stdio_usb_connected() && espera_ms < 15000) {
        sleep_ms(200);
        espera_ms += 200;
    }
    sleep_ms(500); // margen para que el terminal enganche las primeras lineas

    printf("=== hqc_encaps_pico -- HQC-128 (PQClean clean) en RP2040 ===\n");
    printf("PQCLEAN_HQC128_CLEAN_CRYPTO_PUBLICKEYBYTES = %d\n", PQCLEAN_HQC128_CLEAN_CRYPTO_PUBLICKEYBYTES);
    printf("PQCLEAN_HQC128_CLEAN_CRYPTO_CIPHERTEXTBYTES = %d\n", PQCLEAN_HQC128_CLEAN_CRYPTO_CIPHERTEXTBYTES);
    printf("N_MUESTRAS = %d\n\n", N_MUESTRAS);

    printf("Generando keypair (una sola vez, fuera del bucle de medicion)...\n");
    uint64_t t0 = time_us_64();
    int rc = PQCLEAN_HQC128_CLEAN_crypto_kem_keypair(pk, sk);
    uint64_t t1 = time_us_64();
    if (rc != 0) {
        printf("ERROR: crypto_kem_keypair devolvio %d\n", rc);
        while (1) { tight_loop_contents(); }
    }
    printf("keypair: %llu us (informativo, no es la metrica de interes -- el FC no genera "
           "pares efimeros en este diseno)\n\n", (unsigned long long)(t1 - t0));

    printf("Midiendo %d encapsulaciones...\n", N_MUESTRAS);
    for (int i = 0; i < N_MUESTRAS; i++) {
        uint64_t inicio = time_us_64();
        rc = PQCLEAN_HQC128_CLEAN_crypto_kem_enc(ct, ss, pk);
        uint64_t fin = time_us_64();
        if (rc != 0) {
            printf("ERROR: crypto_kem_enc devolvio %d en la muestra %d\n", rc, i);
            while (1) { tight_loop_contents(); }
        }
        muestras_us[i] = fin - inicio;
        if ((i % 50) == 0) {
            printf("  [%d/%d] %llu us\n", i, N_MUESTRAS, (unsigned long long)muestras_us[i]);
        }
    }

    // Copia para ordenar (percentiles) sin perder el orden original, que se vuelca aparte.
    uint64_t ordenadas[N_MUESTRAS];
    memcpy(ordenadas, muestras_us, sizeof(muestras_us));
    qsort(ordenadas, N_MUESTRAS, sizeof(uint64_t), comparar_u64);

    uint64_t suma = 0;
    for (int i = 0; i < N_MUESTRAS; i++) suma += muestras_us[i];
    double media = (double)suma / N_MUESTRAS;
    uint64_t p50 = ordenadas[N_MUESTRAS / 2];
    uint64_t p95 = ordenadas[(N_MUESTRAS * 95) / 100];
    uint64_t minimo = ordenadas[0];
    uint64_t maximo = ordenadas[N_MUESTRAS - 1];

    printf("\n=== Resumen (microsegundos) ===\n");
    printf("media = %.1f\n", media);
    printf("p50   = %llu\n", (unsigned long long)p50);
    printf("p95   = %llu\n", (unsigned long long)p95);
    printf("min   = %llu\n", (unsigned long long)minimo);
    printf("max   = %llu\n", (unsigned long long)maximo);

    printf("\n=== Volcado CSV (todas las muestras, orden de captura) ===\n");
    printf("indice,us\n");
    for (int i = 0; i < N_MUESTRAS; i++) {
        printf("%d,%llu\n", i, (unsigned long long)muestras_us[i]);
    }

    printf("\n=== FIN ===\n");
    while (1) { tight_loop_contents(); }
}
