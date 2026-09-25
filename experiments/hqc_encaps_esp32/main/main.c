// Benchmark de encapsulacion de HQC-128 (PQClean, referencia "clean") en una ESP32
// (Xtensa LX6 dual-core, 240 MHz, con cache -- via ESP-IDF/FreeRTOS).
//
// Por que existe: proyecto hermano de experiments/hqc_encaps_pico/ (RP2040 Cortex-M0+,
// bare-metal), pedido por Javier para acotar mejor el rango de hardware "clase
// autopiloto" que bracketea el Cortex-A9 real del Bebop (no medido) entre el x86 de
// referencia (167.6 us, energy_cpu_bound/) y el RP2040 (57.3 ms) -- ver
// subsec:realtime_control del manuscrito. La ESP32 esta arquitectonicamente mas cerca de
// un nucleo movil moderno (cache, reloj mas alto) que el RP2040, asi que da un tercer
// punto real, no una simulacion.
//
// Que mide: PQCLEAN_HQC128_CLEAN_crypto_kem_enc() -- la operacion que el FC SI hace en
// este diseno (la decapsulacion es de la GCS) -- en microsegundos, con esp_timer_get_time()
// (resolucion de 1 us, temporizador de hardware de la ESP32).
//
// Que NO mide: la keypair (una sola vez, informativo -- el FC no genera pares efimeros en
// este diseno) ni la decapsulacion (tampoco es del FC).

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"

#include "api.h"

#ifndef N_MUESTRAS
#define N_MUESTRAS 500
#endif

static uint8_t pk[PQCLEAN_HQC128_CLEAN_CRYPTO_PUBLICKEYBYTES];
static uint8_t sk[PQCLEAN_HQC128_CLEAN_CRYPTO_SECRETKEYBYTES];
static uint8_t ct[PQCLEAN_HQC128_CLEAN_CRYPTO_CIPHERTEXTBYTES];
static uint8_t ss[PQCLEAN_HQC128_CLEAN_CRYPTO_BYTES];

static int64_t muestras_us[N_MUESTRAS];

static int comparar_i64(const void *a, const void *b) {
    int64_t va = *(const int64_t *)a;
    int64_t vb = *(const int64_t *)b;
    if (va < vb) return -1;
    if (va > vb) return 1;
    return 0;
}

void app_main(void) {
    // margen para que `idf.py monitor` enganche desde el principio
    vTaskDelay(pdMS_TO_TICKS(1500));

    printf("=== hqc_encaps_esp32 -- HQC-128 (PQClean clean) en ESP32 (Xtensa LX6) ===\n");
    printf("PQCLEAN_HQC128_CLEAN_CRYPTO_PUBLICKEYBYTES = %d\n", PQCLEAN_HQC128_CLEAN_CRYPTO_PUBLICKEYBYTES);
    printf("PQCLEAN_HQC128_CLEAN_CRYPTO_CIPHERTEXTBYTES = %d\n", PQCLEAN_HQC128_CLEAN_CRYPTO_CIPHERTEXTBYTES);
    printf("N_MUESTRAS = %d\n\n", N_MUESTRAS);

    printf("Generando keypair (una sola vez, fuera del bucle de medicion)...\n");
    int64_t t0 = esp_timer_get_time();
    int rc = PQCLEAN_HQC128_CLEAN_crypto_kem_keypair(pk, sk);
    int64_t t1 = esp_timer_get_time();
    if (rc != 0) {
        printf("ERROR: crypto_kem_keypair devolvio %d\n", rc);
        while (1) { vTaskDelay(portMAX_DELAY); }
    }
    printf("keypair: %lld us (informativo, no es la metrica de interes -- el FC no genera "
           "pares efimeros en este diseno)\n\n", (long long)(t1 - t0));

    printf("Midiendo %d encapsulaciones...\n", N_MUESTRAS);
    for (int i = 0; i < N_MUESTRAS; i++) {
        int64_t inicio = esp_timer_get_time();
        rc = PQCLEAN_HQC128_CLEAN_crypto_kem_enc(ct, ss, pk);
        int64_t fin = esp_timer_get_time();
        if (rc != 0) {
            printf("ERROR: crypto_kem_enc devolvio %d en la muestra %d\n", rc, i);
            while (1) { vTaskDelay(portMAX_DELAY); }
        }
        muestras_us[i] = fin - inicio;
        if ((i % 50) == 0) {
            printf("  [%d/%d] %lld us\n", i, N_MUESTRAS, (long long)muestras_us[i]);
        }
    }

    int64_t ordenadas[N_MUESTRAS];
    memcpy(ordenadas, muestras_us, sizeof(muestras_us));
    qsort(ordenadas, N_MUESTRAS, sizeof(int64_t), comparar_i64);

    int64_t suma = 0;
    for (int i = 0; i < N_MUESTRAS; i++) suma += muestras_us[i];
    double media = (double)suma / N_MUESTRAS;
    int64_t p50 = ordenadas[N_MUESTRAS / 2];
    int64_t p95 = ordenadas[(N_MUESTRAS * 95) / 100];
    int64_t minimo = ordenadas[0];
    int64_t maximo = ordenadas[N_MUESTRAS - 1];

    printf("\n=== Resumen (microsegundos) ===\n");
    printf("media = %.1f\n", media);
    printf("p50   = %lld\n", (long long)p50);
    printf("p95   = %lld\n", (long long)p95);
    printf("min   = %lld\n", (long long)minimo);
    printf("max   = %lld\n", (long long)maximo);

    printf("\n=== Volcado CSV (todas las muestras, orden de captura) ===\n");
    printf("indice,us\n");
    for (int i = 0; i < N_MUESTRAS; i++) {
        printf("%d,%lld\n", i, (long long)muestras_us[i]);
    }

    printf("\n=== FIN ===\n");
    while (1) { vTaskDelay(portMAX_DELAY); }
}
